"""
xml_serializer.py
Converts decoded resource objects (from dbpf_reader) back into
annotated XML files that can be re-compiled by s2xml_compile.py.

Every XML file produced is valid input for the compiler — full round-trip.
BHAVs get opcode name annotations as XML comments for readability.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

from ttab_ctss_bcon_encoders import TTABResource, CTSSResource, BCONResource
from dbpf_reader import (
    DecodedBHAV, DecodedSTR, DecodedTPRP, DecodedTRCN, DecodedOBJf,
    RawResource, GOTO_NAMES, TYPE_NAMES,
    EXIT_TRUE, EXIT_FALSE, EXIT_ERROR,
)
import opcodes as op_ref

# Language ID → name mapping (inverse of str_encoder.LANGUAGE_IDS)
LANG_NAMES = {
    0:  "default",
    1:  "en-us",   2: "en-uk",
    3:  "french",  4: "german",  5: "italian",
    6:  "spanish", 7: "dutch",   8: "danish",
    9:  "swedish", 10: "norwegian", 11: "finnish",
    12: "hebrew",  13: "russian", 14: "portuguese",
    15: "japanese", 16: "polish", 17: "zh-simple",
    18: "zh-trad", 19: "thai",   20: "korean",
}


def _prettify(elem: ET.Element, xml_declaration: bool = True) -> str:
    """Return a pretty-printed XML string with optional declaration."""
    rough = ET.tostring(elem, encoding="unicode")
    reparsed = minidom.parseString(rough)
    pretty = reparsed.toprettyxml(indent="  ", encoding=None)
    lines = pretty.split("\n")
    # minidom always adds <?xml ...?> — strip or keep based on flag
    if not xml_declaration and lines[0].startswith("<?xml"):
        lines = lines[1:]
    # Drop blank lines minidom sometimes adds
    lines = [l for l in lines if l.strip()]
    return "\n".join(lines)


def _goto_str(v: int) -> str:
    return GOTO_NAMES.get(v, str(v))


# ── Per-type serializers ──────────────────────────────────────────────────────

def _serialize_bhav(res: DecodedBHAV) -> str:
    root = ET.Element("bhav")
    root.set("name",         res.name)
    root.set("group",        f"0x{res.group_id:08X}")
    root.set("instance",     f"0x{res.instance_id:08X}")
    root.set("tree_type",    str(res.tree_type))
    root.set("argc",         str(res.argc))
    root.set("locals",       str(res.locals))
    root.set("flags",        f"0x{res.flags:02X}")
    root.set("tree_version", str(res.tree_version))

    for instr in res.instructions:
        info    = op_ref.lookup(instr.opcode)
        op_name = info["name"]
        labels  = info.get("operands", [""] * 8)
        notes   = info.get("notes", "")

        el = ET.SubElement(root, "instruction")
        el.set("opcode", f"0x{instr.opcode:04X}")
        el.set("true",   _goto_str(instr.goto_true))
        el.set("false",  _goto_str(instr.goto_false))
        el.set("node_version", f"0x{instr.node_version:02X}")
        if getattr(instr, "comment", ""):
            el.set("comment", instr.comment)

        # Operands as individual attrs for readability
        for i, byte_val in enumerate(instr.operands):
            el.set(f"op{i}", f"0x{byte_val:02X}")

        # Comment with opcode name + operand meanings
        comment_parts = [f"[{instr.index}] {op_name}"]
        op_descs = []
        for i, (val, lbl) in enumerate(zip(instr.operands, labels)):
            if lbl:
                op_descs.append(f"op{i}={val} ({lbl})")
        if op_descs:
            comment_parts.append(", ".join(op_descs))
        if notes:
            comment_parts.append(f"  NOTE: {notes}")

        el.append(ET.Comment(" " + " | ".join(comment_parts) + " "))

    return _prettify(root)


def _serialize_str(res: DecodedSTR) -> str:
    root = ET.Element("str")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")

    for entry in res.entries:
        el = ET.SubElement(root, "entry")
        el.set("value",       entry.value)
        el.set("description", entry.description)
        el.set("language",    LANG_NAMES.get(entry.language_id, str(entry.language_id)))

    return _prettify(root)


def _serialize_tprp(res: DecodedTPRP) -> str:
    root = ET.Element("tprp")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")

    for p in res.params:
        el = ET.SubElement(root, "param")
        el.set("name",  p.name)
        el.set("label", p.label)

    for l in res.locals_:
        el = ET.SubElement(root, "local")
        el.set("name",  l.name)
        el.set("label", l.label)

    return _prettify(root)


def _serialize_trcn(res: DecodedTRCN) -> str:
    root = ET.Element("trcn")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")

    for e in res.entries:
        el = ET.SubElement(root, "constant")
        el.set("name",        e.name)
        el.set("value",       str(e.value))
        el.set("description", e.description)
        if not e.enabled:
            el.set("enabled", "false")

    return _prettify(root)


def _serialize_objf(res: DecodedOBJf) -> str:
    root = ET.Element("objf")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")

    for i, slot in enumerate(res.entries):
        el = ET.SubElement(root, "slot")
        el.set("action", f"0x{slot.action_bhav:08X}")
        el.set("guard",  f"0x{slot.guard_bhav:08X}")
        el.append(ET.Comment(f" Slot {i} "))

    return _prettify(root)


def _serialize_raw(res: RawResource) -> str:
    """Emit a placeholder XML for unrecognised resource types."""
    tname = TYPE_NAMES.get(res.type_id, f"0x{res.type_id:08X}")
    root = ET.Element("raw_resource")
    root.set("type_id",    f"0x{res.type_id:08X}")
    root.set("type_name",  tname)
    root.set("group",      f"0x{res.group_id:08X}")
    root.set("instance",   f"0x{res.instance_id:08X}")
    root.set("size_bytes", str(len(res.data)))
    root.append(ET.Comment(" This resource type is not yet supported by the S2XML decompiler. "))
    root.text = res.data.hex()
    return _prettify(root)


# ── Dispatch ──────────────────────────────────────────────────────────────────

def _serialize_ttab(res) -> str:
    from ttab_ctss_bcon_encoders import MOTIVES, TTAB_FLAG_IS_AUTONOMOUS, AGE_ALL
    root = ET.Element("ttab")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")
    for i, entry in enumerate(res.entries):
        el = ET.SubElement(root, "slot")
        el.set("action",    f"0x{entry.action:04X}")
        el.set("guard",     f"0x{entry.guard:04X}")
        el.set("str_index", str(entry.str_index))
        el.set("autonomy",  str(entry.autonomy))
        el.set("flags",     f"0x{entry.flags:08X}")
        el.set("age_flags", f"0x{entry.age_flags:04X}")
        # Only emit motives if any are non-zero
        if any(m != 0 for m in entry.motives):
            el.set("motives", ",".join(str(m) for m in entry.motives))
        # Comment with human-readable flag/age info
        flag_names = []
        if entry.flags & 0x04: flag_names.append("autonomous")
        if entry.flags & 0x08: flag_names.append("not-available")
        if entry.flags & 0x20: flag_names.append("always-in-menu")
        age_parts = []
        for bit, label in [(0x04,"child"),(0x08,"teen"),(0x10,"adult"),(0x20,"elder")]:
            if entry.age_flags & bit:
                age_parts.append(label)
        comment = f" Slot {i}"
        if flag_names: comment += f" | flags: {', '.join(flag_names)}"
        if age_parts:  comment += f" | ages: {', '.join(age_parts)}"
        el.append(ET.Comment(comment + " "))
    return _prettify(root)


def _serialize_ctss(res) -> str:
    root = ET.Element("ctss")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")
    for entry in res.entries:
        el = ET.SubElement(root, "entry")
        el.set("instance",    f"0x{entry.instance:04X}")
        el.set("language",    LANG_NAMES.get(entry.language_id, str(entry.language_id)))
        el.set("obj_name",    entry.obj_name)
        el.set("description", entry.description)
    return _prettify(root)


def _serialize_bcon(res) -> str:
    root = ET.Element("bcon")
    root.set("name",     res.name)
    root.set("group",    f"0x{res.group_id:08X}")
    root.set("instance", f"0x{res.instance_id:08X}")
    for i, val in enumerate(res.values):
        el = ET.SubElement(root, "constant")
        el.set("index", str(i))
        el.set("value", str(val))
    return _prettify(root)


SERIALIZERS = {
    DecodedBHAV: ("bhav", _serialize_bhav),
    DecodedSTR:  ("str",  _serialize_str),
    DecodedTPRP: ("tprp", _serialize_tprp),
    DecodedTRCN: ("trcn", _serialize_trcn),
    DecodedOBJf: ("objf", _serialize_objf),
    RawResource:   ("raw",  _serialize_raw),
    TTABResource:  ("ttab", _serialize_ttab),
    CTSSResource:  ("ctss", _serialize_ctss),
    BCONResource:  ("bcon", _serialize_bcon),
}


def resource_filename(res) -> str:
    """
    Build a descriptive filename for a decoded resource.
    Format: <sanitised_name>.<type>.xml
    e.g. "Secret_Rendezvous_-_Main.bhav.xml"
    """
    ext, _ = SERIALIZERS.get(type(res), ("unknown", None))

    # Use name attr if available, else fall back to instance ID
    raw_name = getattr(res, "name", None) or f"0x{res.instance_id:08X}"
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in raw_name)
    safe_name = safe_name.strip().replace(" ", "_")[:64] or "resource"

    return f"{safe_name}.{ext}.xml"


def serialize_resource(res, bhav_map: dict = None) -> str:
    """
    Return XML string for any decoded resource.
    bhav_map: optional dict of instance_id → DecodedBHAV, used to fix TPRP splits.
    """
    from dbpf_reader import DecodedTPRP
    if isinstance(res, DecodedTPRP) and bhav_map:
        bhav = bhav_map.get(res.instance_id)
        argc = bhav.argc if bhav else 0
        return _serialize_tprp(res, bhav_argc=argc)
    _, fn = SERIALIZERS.get(type(res), ("raw", _serialize_raw))
    return fn(res)


def write_resource_xml(res, out_dir: Path, bhav_map: dict = None) -> Path:
    """Write a decoded resource to <out_dir>/<filename>.xml. Returns the path."""
    filename = resource_filename(res)
    out_path = out_dir / filename

    # Handle filename collisions (e.g. two BHAVs with same name)
    stem, *rest = filename.rsplit(".", 2)
    suffix = ".".join(rest) if rest else "xml"
    counter = 1
    while out_path.exists():
        out_path = out_dir / f"{stem}_{counter}.{suffix}"
        counter += 1

    xml_str = serialize_resource(res, bhav_map=bhav_map)
    out_path.write_text(xml_str, encoding="utf-8")
    return out_path
