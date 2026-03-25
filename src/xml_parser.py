"""
xml_parser.py
Each XML file defines exactly ONE Sims 2 resource.
The root element tag determines the resource type:

  <bhav>   → BHAV (Behaviour)        type 0x42484156
  <str>    → STR# (String Table)     type 0x53545223
  <tprp>   → TPRP (Tree Properties)  type 0x54505250
  <trcn>   → TRCN (Tree Constants)   type 0x5452434E
  <objf>   → OBJf (Object Functions) type 0x4F424A66

Every root element requires:
  name       human-readable resource name (shown in SimPE)
  group      hex group ID  (default 0x7FD46CD0 = local group)
  instance   hex instance ID (must be unique per type within a package)

Returns a single (type_id, group_id, instance_id, data_bytes) tuple.
"""

import xml.etree.ElementTree as ET
from typing import Tuple

from bhav_encoder      import BHAVResource, BHAVInstruction, EXIT_TRUE, EXIT_FALSE, EXIT_ERROR
from str_encoder       import STRResource, LANGUAGE_IDS
from misc_encoders     import TPRPResource, TPRPEntry, TRCNResource, TRCNEntry, OBJfResource
from glob_objd_encoders import parse_glob_xml, parse_objd_xml, TYPE_GLOB, TYPE_OBJD
from ttab_ctss_bcon_encoders import (
    TTABResource, TTABEntry, TTAB_FLAG_IS_AUTONOMOUS, AGE_ALL,
    CTSSResource, BCONResource,
    TYPE_TTAB, TYPE_CTSS, TYPE_BCON,
)

# ── DBPF type IDs ───────────────────────────────────────────────────────────
TYPE_BHAV = 0x42484156
TYPE_STR  = 0x53545223
TYPE_TPRP = 0x54505250
TYPE_TRCN = 0x5452434E
TYPE_OBJf = 0x4F424A66

# ── goto shorthand aliases ───────────────────────────────────────────────────
GOTO_ALIASES = {
    "true":       EXIT_TRUE,
    "false":      EXIT_FALSE,
    "error":      EXIT_ERROR,
    "exit_true":  EXIT_TRUE,
    "exit_false": EXIT_FALSE,
}

DEFAULT_GROUP = 0x7FD46CD0   # local/private mod group

# Global constant table — populated by two-pass compile from TRCN/BCON resources
# Maps name → int value. Set by the compiler before parsing BHAVs.
_GLOBAL_CONSTANTS: dict = {}


def set_global_constants(constants: dict) -> None:
    """Called by the compiler after collecting TRCN/BCON resources."""
    global _GLOBAL_CONSTANTS
    _GLOBAL_CONSTANTS = dict(constants)


def _int(s, default=0) -> int:
    if s is None:
        return default
    s = s.strip()
    if not s:
        return default
    try:
        return int(s, 0)
    except ValueError:
        return default


def _goto(s) -> int:
    if s is None:
        return EXIT_TRUE
    s = s.strip().lower()
    return GOTO_ALIASES.get(s, _int(s, EXIT_TRUE))


def _attr(el, *names, default=""):
    for n in names:
        v = el.get(n)
        if v is not None:
            return v
    return default


# ── Resource parsers ─────────────────────────────────────────────────────────

def _parse_bhav(root):
    name      = _attr(root, "name",     default="Untitled BHAV")
    group_id  = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id   = _int(_attr(root, "instance", "inst"), 0x1000)
    tree_type = _int(root.get("tree_type"),  0)
    argc      = _int(root.get("argc"),       0)
    locals_   = _int(root.get("locals"),     0)
    flags     = _int(root.get("flags"),      0x01)
    tree_ver  = _int(root.get("tree_version"), 0)

    bhav = BHAVResource(
        name=name, tree_type=tree_type, argc=argc,
        locals=locals_, flags=flags, tree_version=tree_ver,
    )

    # Two-pass: collect any inline <constants> child for $CONST resolution
    constants = _GLOBAL_CONSTANTS.copy()
    const_block = root.find("constants")
    if const_block is not None:
        for c in const_block.findall("constant"):
            cname = c.get("name", "")
            cval  = _int(c.get("value"), 0)
            if cname:
                constants[cname] = cval

    from bhav_xml_helpers import parse_bhav_element
    try:
        bhav.instructions = parse_bhav_element(root, constants)
    except ValueError as e:
        raise ValueError(f"BHAV '{name}': {e}") from e

    return (TYPE_BHAV, group_id, inst_id, bhav.encode())


def _parse_str(root):
    name     = _attr(root, "name",    default="Untitled STR")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x0001)

    res = STRResource(name=name)
    for el in root.findall("entry"):
        value   = el.get("value", "") or (el.text or "").strip()
        desc    = el.get("description", el.get("desc", ""))
        lang    = el.get("language", el.get("lang", "en-us")).lower()
        lang_id = LANGUAGE_IDS.get(lang, 1)
        res.add(value, desc, lang)

    return (TYPE_STR, group_id, inst_id, res.encode())


def _parse_tprp(root):
    name     = _attr(root, "name",    default="Untitled TPRP")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x1000)

    res = TPRPResource(bhav_name=name)
    for el in root.findall("param"):
        res.params.append(TPRPEntry(name=el.get("name", "param"), label=el.get("label", "")))
    for el in root.findall("local"):
        res.locals_.append(TPRPEntry(name=el.get("name", "local"), label=el.get("label", "")))
    return (TYPE_TPRP, group_id, inst_id, res.encode())


def _parse_trcn(root):
    name     = _attr(root, "name",    default="Untitled TRCN")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x1000)

    res = TRCNResource(name=name)
    for el in root.findall("constant"):
        res.entries.append(TRCNEntry(
            name=el.get("name", "Const"),
            value=_int(el.get("value"), 0),
            description=el.get("description", el.get("desc", "")),
        ))
    return (TYPE_TRCN, group_id, inst_id, res.encode())


def _parse_objf(root):
    name     = _attr(root, "name",    default="Untitled OBJf")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x0001)

    res = OBJfResource(name=name)
    for el in root.findall("slot"):
        res.add(_int(el.get("action"), 0), _int(el.get("guard"), 0))
    return (TYPE_OBJf, group_id, inst_id, res.encode())


# ── Dispatch ─────────────────────────────────────────────────────────────────

def _parse_ttab(root):
    name     = _attr(root, "name",     default="Untitled TTAB")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x0001)
    res = TTABResource(name=name)
    for el in root.findall("slot"):
        motives = [0] * 16
        mstr = el.get("motives", "")
        if mstr:
            for i, v in enumerate(mstr.split(",")[:16]):
                motives[i] = int(v.strip(), 0) & 0xFF
        res.add(
            action      = _int(el.get("action"),    0),
            guard       = _int(el.get("guard"),     0),
            str_index   = _int(el.get("str_index"), 0),
            autonomy    = _int(el.get("autonomy"),  0),
            flags       = _int(el.get("flags"),     TTAB_FLAG_IS_AUTONOMOUS),
            age_flags   = _int(el.get("age_flags"), AGE_ALL),
            motives     = motives,
        )
    return (TYPE_TTAB, group_id, inst_id, res.encode())


def _parse_ctss(root):
    from str_encoder import LANGUAGE_IDS
    name     = _attr(root, "name",     default="Untitled CTSS")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x0001)
    res = CTSSResource(name=name)
    for el in root.findall("entry"):
        lang = el.get("language", el.get("lang", "en-us")).lower()
        res.add(
            obj_name    = el.get("obj_name",    el.get("name", "")),
            description = el.get("description", el.get("desc", "")),
            instance    = _int(el.get("instance"), 0x0001),
            language    = lang,
        )
    return (TYPE_CTSS, group_id, inst_id, res.encode())


def _parse_bcon(root):
    name     = _attr(root, "name",     default="Untitled BCON")
    group_id = _int(_attr(root, "group"),           DEFAULT_GROUP)
    inst_id  = _int(_attr(root, "instance", "inst"), 0x0001)
    res = BCONResource(name=name)
    for el in root.findall("constant"):
        res.add(_int(el.get("value"), 0))
    return (TYPE_BCON, group_id, inst_id, res.encode())


PARSERS = {
    "bhav": _parse_bhav,
    "str":  _parse_str,
    "tprp": _parse_tprp,
    "trcn": _parse_trcn,
    "objf": _parse_objf,
    "glob": parse_glob_xml,
    "objd": parse_objd_xml,
    "ttab": _parse_ttab,
    "ctss": _parse_ctss,
    "bcon": _parse_bcon,
}

TYPE_NAMES = {
    TYPE_BHAV: "BHAV",
    TYPE_STR:  "STR#",
    TYPE_TPRP: "TPRP",
    TYPE_TRCN: "TRCN",
    TYPE_OBJf: "OBJf",
    TYPE_GLOB: "GLOB",
    TYPE_OBJD: "OBJD",
    TYPE_TTAB: "TTAB",
    TYPE_CTSS: "CTSS",
    TYPE_BCON: "BCON",
}


def parse_resource_xml(xml_path: str) -> Tuple[int, int, int, bytes]:
    """
    Parse a single-resource XML file.
    Returns (type_id, group_id, instance_id, data_bytes).
    Raises ValueError on any error.
    """
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        raise ValueError(f"XML syntax error: {e}")

    root = tree.getroot()
    tag  = root.tag.lower()

    if tag not in PARSERS:
        supported = ", ".join(f"<{k}>" for k in PARSERS)
        raise ValueError(
            f"Unknown root element <{root.tag}>. Supported: {supported}"
        )

    try:
        return PARSERS[tag](root)
    except Exception as e:
        raise ValueError(f"Error building {tag.upper()} resource: {e}") from e
