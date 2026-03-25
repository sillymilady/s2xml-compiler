"""
dbpf_reader.py
Reads a DBPF 1.1 .package file and decodes each known resource type
back into Python data structures, ready to be serialized as XML.

Supports: BHAV, STR#, TPRP, TRCN, OBJf
Unknown resource types are preserved as raw blobs.
"""

import struct
from dataclasses import dataclass, field
from typing import Optional

# ── Type IDs ─────────────────────────────────────────────────────────────────
TYPE_BHAV = 0x42484156
TYPE_STR  = 0x53545223
TYPE_TPRP = 0x54505250
TYPE_TRCN = 0x5452434E
TYPE_OBJf = 0x4F424A66
TYPE_GLOB = 0x474C4F42
TYPE_OBJD = 0x4F424A44
TYPE_SLOT = 0x534C4F54  # SLOT (routing slot descriptor)
TYPE_TTAB = 0x54544142  # TTAB (pie menu interaction table)
TYPE_MMAT = 0x4D4D4154  # MMAT (material override)
TYPE_TTAB = 0x54544142  # TTAB (pie menu table)
TYPE_CTSS = 0x43545353  # CTSS (catalog description)
TYPE_BCON = 0x42434F4E  # BCON (behaviour constant)

TYPE_NAMES = {
    TYPE_BHAV: "BHAV",
    TYPE_STR:  "STR#",
    TYPE_TPRP: "TPRP",
    TYPE_TRCN: "TRCN",
    TYPE_OBJf: "OBJf",
    TYPE_GLOB: "GLOB",
    TYPE_OBJD: "OBJD",
    TYPE_SLOT: "SLOT",
    TYPE_TTAB: "TTAB",
    TYPE_MMAT: "MMAT",
    TYPE_TTAB: "TTAB",
    TYPE_CTSS: "CTSS",
    TYPE_BCON: "BCON",
}

EXIT_TRUE  = 0xFD
EXIT_FALSE = 0xFE
EXIT_ERROR = 0xFF

GOTO_NAMES = {EXIT_TRUE: "true", EXIT_FALSE: "false", EXIT_ERROR: "error"}


# ── Decoded resource dataclasses ──────────────────────────────────────────────

@dataclass
class DecodedBHAV:
    type_id:      int = TYPE_BHAV
    name:         str = ""
    group_id:     int = 0
    instance_id:  int = 0
    format:       int = 0x8008
    tree_type:    int = 0
    argc:         int = 0
    locals:       int = 0
    flags:        int = 0x01
    tree_version: int = 0
    instructions: list = field(default_factory=list)


@dataclass
class DecodedInstruction:
    index:        int
    opcode:       int
    goto_true:    int
    goto_false:   int
    node_version: int
    operands:     list
    comment:      str = ""   # user annotation — not in binary


@dataclass
class DecodedSTREntry:
    language_id: int
    value:       str
    description: str


@dataclass
class DecodedSTR:
    type_id:     int = TYPE_STR
    name:        str = ""
    group_id:    int = 0
    instance_id: int = 0
    format:      int = 0x0042
    entries:     list = field(default_factory=list)


@dataclass
class DecodedTPRPEntry:
    name:  str
    label: str


@dataclass
class DecodedTPRP:
    type_id:     int = TYPE_TPRP
    name:        str = ""
    group_id:    int = 0
    instance_id: int = 0
    params:      list = field(default_factory=list)
    locals_:     list = field(default_factory=list)


@dataclass
class DecodedTRCNEntry:
    name:        str
    value:       int
    description: str
    enabled:     bool = True


@dataclass
class DecodedTRCN:
    type_id:     int = TYPE_TRCN
    name:        str = ""
    group_id:    int = 0
    instance_id: int = 0
    entries:     list = field(default_factory=list)


@dataclass
class DecodedOBJfEntry:
    action_bhav: int
    guard_bhav:  int


@dataclass
class DecodedOBJf:
    type_id:     int = TYPE_OBJf
    name:        str = ""
    group_id:    int = 0
    instance_id: int = 0
    entries:     list = field(default_factory=list)


@dataclass
class RawResource:
    """Fallback for unsupported resource types."""
    type_id:     int
    group_id:    int
    instance_id: int
    data:        bytes
    name:        str = ""   # populated if we can read the name header


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_pstring(data: bytes, offset: int) -> tuple:
    length = data[offset]
    text = data[offset + 1: offset + 1 + length].decode("latin-1", errors="replace")
    return text, offset + 1 + length


def _read_name_header(data: bytes) -> tuple:
    """Read uint16 name_len + null-terminated name. Returns (name, cursor)."""
    if len(data) < 2:
        return "", 0
    name_len = struct.unpack_from("<H", data, 0)[0]
    if name_len == 0 or 2 + name_len > len(data):
        return "", 2
    name = data[2: 2 + name_len - 1].decode("latin-1", errors="replace")
    return name, 2 + name_len


def _try_read_name(data: bytes) -> str:
    """Best-effort read of the name header, returns empty string on failure."""
    try:
        name, _ = _read_name_header(data)
        # Sanity check: name should be printable ASCII
        if all(32 <= ord(c) < 127 or c in " -_()[]" for c in name):
            return name
    except Exception:
        pass
    return ""


# ── Decoders ──────────────────────────────────────────────────────────────────

def _decode_bhav(data: bytes, group_id: int, instance_id: int) -> DecodedBHAV:
    name, cur = _read_name_header(data)

    if cur + 12 > len(data):
        raise ValueError(f"BHAV too short after name (need 12 header bytes, have {len(data)-cur})")

    fmt, count, tree_type, argc, locals_, flags, tree_ver = struct.unpack_from("<HHBBBBi", data, cur)
    cur += 12  # 2+2+1+1+1+1+4

    # TS2 format 0x8008 = 14 bytes/instruction; TS1 0x8007 = 12 bytes
    instr_size = 14 if fmt >= 0x8008 else 12

    instructions = []
    for i in range(count):
        if cur + instr_size > len(data):
            break
        chunk = data[cur: cur + instr_size]
        opcode = struct.unpack_from("<H", chunk, 0)[0]
        gt, gf = chunk[2], chunk[3]
        if instr_size == 14:
            node_ver = chunk[4]
            ops = list(chunk[6:14])
        else:
            node_ver = 0xFE
            ops = list(chunk[4:12])
        instructions.append(DecodedInstruction(i, opcode, gt, gf, node_ver, ops))
        cur += instr_size

    return DecodedBHAV(
        type_id=TYPE_BHAV, name=name, group_id=group_id, instance_id=instance_id,
        format=fmt, tree_type=tree_type, argc=argc, locals=locals_,
        flags=flags, tree_version=tree_ver, instructions=instructions,
    )


def _decode_str(data: bytes, group_id: int, instance_id: int) -> DecodedSTR:
    name, cur = _read_name_header(data)
    fmt, count = struct.unpack_from("<HH", data, cur)
    cur += 4

    entries = []
    for _ in range(count):
        if cur >= len(data):
            break
        lang_id = data[cur]; cur += 1
        value, cur = _read_pstring(data, cur)
        desc,  cur = _read_pstring(data, cur)
        entries.append(DecodedSTREntry(lang_id, value, desc))

    return DecodedSTR(type_id=TYPE_STR, name=name, group_id=group_id,
                      instance_id=instance_id, format=fmt, entries=entries)


def _decode_tprp(data: bytes, group_id: int, instance_id: int) -> DecodedTPRP:
    name, cur = _read_name_header(data)
    fmt, count = struct.unpack_from("<HH", data, cur)
    cur += 4

    entries = []
    for _ in range(count):
        if cur >= len(data):
            break
        n, cur = _read_pstring(data, cur)
        l, cur = _read_pstring(data, cur)
        entries.append(DecodedTPRPEntry(n, l))

    # TPRP binary doesn't encode param/local split — store all as params
    # (the compiler accepts both <param> and <local>, caller can re-split)
    return DecodedTPRP(type_id=TYPE_TPRP, name=name, group_id=group_id,
                       instance_id=instance_id, params=entries, locals_=[])


def _decode_trcn(data: bytes, group_id: int, instance_id: int) -> DecodedTRCN:
    name, cur = _read_name_header(data)
    fmt, count = struct.unpack_from("<HH", data, cur)
    cur += 4

    entries = []
    for _ in range(count):
        if cur >= len(data):
            break
        flag = data[cur]; cur += 1
        value = struct.unpack_from("<h", data, cur)[0]; cur += 2
        n, cur = _read_pstring(data, cur)
        d, cur = _read_pstring(data, cur)
        entries.append(DecodedTRCNEntry(n, value, d, bool(flag)))

    return DecodedTRCN(type_id=TYPE_TRCN, name=name, group_id=group_id,
                       instance_id=instance_id, entries=entries)


def _decode_objf(data: bytes, group_id: int, instance_id: int) -> DecodedOBJf:
    name, cur = _read_name_header(data)
    fmt, count = struct.unpack_from("<HH", data, cur)
    cur += 4

    entries = []
    for _ in range(count):
        if cur + 8 > len(data):
            break
        action, guard = struct.unpack_from("<II", data, cur); cur += 8
        entries.append(DecodedOBJfEntry(action, guard))

    return DecodedOBJf(type_id=TYPE_OBJf, name=name, group_id=group_id,
                       instance_id=instance_id, entries=entries)


def _decode_ttab(data: bytes, group_id: int, instance_id: int):
    from ttab_ctss_bcon_encoders import TTABResource
    res = TTABResource.decode(data, group_id, instance_id)
    res.type_id     = TYPE_TTAB
    res.group_id    = group_id
    res.instance_id = instance_id
    return res


def _decode_ctss(data: bytes, group_id: int, instance_id: int):
    from ttab_ctss_bcon_encoders import CTSSResource
    res = CTSSResource.decode(data, group_id, instance_id)
    res.type_id     = TYPE_CTSS
    res.group_id    = group_id
    res.instance_id = instance_id
    return res


def _decode_bcon(data: bytes, group_id: int, instance_id: int):
    from ttab_ctss_bcon_encoders import BCONResource
    res = BCONResource.decode(data, group_id, instance_id)
    res.type_id     = TYPE_BCON
    res.group_id    = group_id
    res.instance_id = instance_id
    return res


# ── Dispatch ──────────────────────────────────────────────────────────────────

DECODERS = {
    TYPE_BHAV: _decode_bhav,
    TYPE_STR:  _decode_str,
    TYPE_TPRP: _decode_tprp,
    TYPE_TRCN: _decode_trcn,
    TYPE_OBJf: _decode_objf,
    TYPE_TTAB: _decode_ttab,
    TYPE_CTSS: _decode_ctss,
    TYPE_BCON: _decode_bcon,
}


# ── DBPF reader ───────────────────────────────────────────────────────────────

def _is_qfs_compressed(data: bytes) -> bool:
    """Detect QFS/RefPack compressed data (magic bytes 0x10FB or 0xFB10)."""
    if len(data) < 2:
        return False
    return data[0] == 0x10 and data[1] == 0xFB


def _qfs_decompress(data: bytes) -> bytes:
    """
    Decompress QFS/RefPack compressed data used in TS2 packages.

    QFS is a variant of EA's RefPack compression. Algorithm:
      - Read a header to get uncompressed size
      - Process control bytes with literals and back-references
    """
    if not _is_qfs_compressed(data):
        return data   # not actually compressed

    offset = 0
    flags    = data[offset]; offset += 1
    magic    = data[offset]; offset += 1   # 0xFB

    # flags bit 0x01 = has uncompressed size in header
    has_size = bool(flags & 0x01)
    compressed_size = 0

    if has_size:
        compressed_size = (data[offset] << 16 | data[offset+1] << 8 | data[offset+2])
        offset += 3

    decomp_size = (data[offset] << 16 | data[offset+1] << 8 | data[offset+2])
    offset += 3

    out = bytearray()

    while offset < len(data):
        b0 = data[offset]; offset += 1

        if b0 <= 0x7F:                          # 2-byte control: copy + literal
            b1 = data[offset]; offset += 1
            num_plain = b0 & 0x03
            num_copy  = ((b0 & 0x1C) >> 2) + 3
            copy_offset = ((b0 & 0x60) << 3) + b1 + 1
            out += data[offset: offset + num_plain]; offset += num_plain
            src = len(out) - copy_offset
            for k in range(num_copy):
                out.append(out[src + k] if src + k < len(out) else 0)

        elif b0 <= 0xBF:                         # 3-byte control
            b1 = data[offset]; offset += 1
            b2 = data[offset]; offset += 1
            num_plain = b1 >> 6 & 0x03
            num_copy  = (b0 & 0x3F) + 4
            copy_offset = ((b1 & 0x3F) << 8) + b2 + 1
            out += data[offset: offset + num_plain]; offset += num_plain
            src = len(out) - copy_offset
            for k in range(num_copy):
                out.append(out[src + k] if src + k < len(out) else 0)

        elif b0 <= 0xDF:                         # 4-byte control
            b1 = data[offset]; offset += 1
            b2 = data[offset]; offset += 1
            b3 = data[offset]; offset += 1
            num_plain = b0 & 0x03
            num_copy  = ((b0 & 0x0C) << 6) + b3 + 5
            copy_offset = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            out += data[offset: offset + num_plain]; offset += num_plain
            src = len(out) - copy_offset
            for k in range(num_copy):
                out.append(out[src + k] if src + k < len(out) else 0)

        elif b0 <= 0xFB:                         # short literal run
            num_plain = ((b0 & 0x1F) << 2) + 4
            out += data[offset: offset + num_plain]; offset += num_plain

        else:                                    # end-of-stream literal
            num_plain = b0 & 0x03
            out += data[offset: offset + num_plain]; offset += num_plain
            break

    return bytes(out)


def read_package(pkg_path: str) -> list:
    """
    Read a .package and return a list of decoded resource objects.
    Each is one of: DecodedBHAV | DecodedSTR | DecodedTPRP | DecodedTRCN |
                    DecodedOBJf | RawResource
    Raises ValueError on malformed DBPF.
    """
    data = open(pkg_path, "rb").read()

    if data[:4] != b"DBPF":
        raise ValueError(f"Not a DBPF file: {pkg_path}")

    major = struct.unpack_from("<I", data, 4)[0]
    if major != 1:
        raise ValueError(f"Unsupported DBPF major version {major} (expected 1)")

    idx_count  = struct.unpack_from("<I", data, 48)[0]
    idx_offset = struct.unpack_from("<I", data, 52)[0]

    # Check for compressed index (DIR resource = type 0xE86B1EEF)
    compressed_insts: set[int] = set()
    for i in range(idx_count):
        off = idx_offset + i * 20
        type_id_check = struct.unpack_from("<I", data, off)[0]
        if type_id_check == 0xE86B1EEF:  # DIR / hole index type = compressed list
            # The DIR entry payload lists (type, group, inst) of compressed resources
            _, _, _, dir_off, dir_size = struct.unpack_from("<IIIII", data, off)
            dir_data = data[dir_off: dir_off + dir_size]
            for j in range(0, len(dir_data), 12):
                if j + 12 > len(dir_data):
                    break
                _, _, cinst = struct.unpack_from("<III", dir_data, j)
                compressed_insts.add(cinst)

    resources = []
    for i in range(idx_count):
        off = idx_offset + i * 20
        type_id, group_id, inst_id, res_off, res_size = struct.unpack_from("<IIIII", data, off)

        # Skip the DIR resource itself
        if type_id == 0xE86B1EEF:
            continue

        res_data = data[res_off: res_off + res_size]

        # Decompress if needed (QFS/RefPack detection)
        if inst_id in compressed_insts or _is_qfs_compressed(res_data):
            try:
                res_data = _qfs_decompress(res_data)
            except Exception as e:
                tname = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
                print(f"  [warn] Could not decompress {tname} inst=0x{inst_id:08X}: {e} — kept as compressed raw")
                raw = RawResource(type_id, group_id, inst_id, res_data,
                                  name=_try_read_name(res_data))
                resources.append(raw)
                continue

        if type_id in DECODERS:
            try:
                decoded = DECODERS[type_id](res_data, group_id, inst_id)
                resources.append(decoded)
                continue
            except Exception as e:
                tname = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
                print(f"  [warn] Could not decode {tname} inst=0x{inst_id:08X}: {e} — kept as raw")

        # Fallback: raw blob
        raw = RawResource(type_id, group_id, inst_id, res_data,
                          name=_try_read_name(res_data))
        resources.append(raw)

    return resources
