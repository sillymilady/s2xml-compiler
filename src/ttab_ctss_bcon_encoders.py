"""
ttab_ctss_bcon_encoders.py
Encoders + decoders for three commonly needed TS2 resource types:

  TTAB  0x54544142  Pie Menu Table — controls each interaction's properties
                    (autonomy, advertising, allowed ages, flags, etc.)
                    Sits alongside OBJf; one TTAB entry per OBJf slot.

  CTSS  0x43545353  Catalog String — buy/build mode description text for objects.
                    Unlike STR#, entries are keyed by instance, not slot order.

  BCON  0x42434F4E  Behaviour Constant — simpler predecessor to TRCN.
                    An array of int16 constants, accessed by index from BHAVs.
"""

import struct
from dataclasses import dataclass, field
from typing import List

TYPE_TTAB = 0x54544142
TYPE_CTSS = 0x43545353
TYPE_BCON = 0x42434F4E


def _pstr(s: str) -> bytes:
    b = s.encode("latin-1", errors="replace")[:255]
    return bytes([len(b)]) + b


def _name_hdr(name: str) -> bytes:
    nb = name.encode("latin-1") + b"\x00"
    return struct.pack("<H", len(nb)) + nb


def _read_name(data: bytes) -> tuple:
    if len(data) < 2:
        return "", 0
    nl = struct.unpack_from("<H", data, 0)[0]
    if nl == 0 or 2 + nl > len(data):
        return "", 2
    name = data[2: 2 + nl - 1].decode("latin-1", errors="replace")
    return name, 2 + nl


def _read_pstring(data: bytes, offset: int) -> tuple:
    length = data[offset]
    return data[offset+1:offset+1+length].decode("latin-1", errors="replace"), offset+1+length


# ── TTAB ─────────────────────────────────────────────────────────────────────
#
# TTAB binary layout (SimPE TTABReader):
#   name_len uint16
#   name     char[]  (null-terminated)
#   format   uint16  (0x000B = TS2 base game format)
#   count    uint16  number of entries
#
# Per entry (format 0x000B = 66 bytes):
#   action      uint16   BHAV instance (action)
#   guard       uint16   BHAV instance (guard / test)
#   str_index   uint16   STR# entry index for pie menu label
#   sentinel    uint16   (0)
#   attenuation float32  advertising attenuation (0.0 = none)
#   autonomy    uint16   autonomy score (0-100, higher = more autonomous)
#   num_attrs   uint16   number of object attribute changes
#   flags       uint32   interaction flags (see below)
#   age_flags   uint16   allowed ages bitmask (see below)
#   motives     int8[16] motive advertising (comfort, hygiene, fun, social, hunger, etc.)
#   pad         uint8[6] padding to 66 bytes

TTAB_FORMAT  = 0x000B
TTAB_ENTRY_SIZE = 66

# flags bitmask
TTAB_FLAG_SHOW_IF_UNAVAIL    = 0x00000001
TTAB_FLAG_JOINABLE           = 0x00000002
TTAB_FLAG_IS_AUTONOMOUS      = 0x00000004
TTAB_FLAG_NOT_AVAILABLE      = 0x00000008
TTAB_FLAG_RUN_IMMEDIATELY    = 0x00000010
TTAB_FLAG_ALWAYS_IN_MENU     = 0x00000020
TTAB_FLAG_FOR_PREPARATION    = 0x00000040
TTAB_FLAG_ADULT_ONLY         = 0x00000100
TTAB_FLAG_SMART_TEST_FROM_PI = 0x00000200
TTAB_FLAG_DEBUG              = 0x00001000

# age_flags bitmask
AGE_BABY    = 0x0001
AGE_TODDLER = 0x0002
AGE_CHILD   = 0x0004
AGE_TEEN    = 0x0008
AGE_ADULT   = 0x0010
AGE_ELDER   = 0x0020
AGE_ALL     = 0x003F  # all ages

# Motive indices (motives[i])
MOTIVES = [
    "comfort", "hygiene", "fun", "social",
    "hunger", "bladder", "energy", "environment",
    "unused8", "unused9", "unused10", "unused11",
    "unused12", "unused13", "unused14", "unused15",
]


@dataclass
class TTABEntry:
    action:      int   = 0       # BHAV instance (action) — uint16
    guard:       int   = 0       # BHAV instance (guard) — uint16
    str_index:   int   = 0       # STR# label index — uint16
    attenuation: float = 0.0     # advertising attenuation — float32
    autonomy:    int   = 0       # autonomy score 0-100 — uint16
    num_attrs:   int   = 0       # attribute changes — uint16
    flags:       int   = TTAB_FLAG_IS_AUTONOMOUS   # uint32
    age_flags:   int   = AGE_ALL                   # uint16
    motives:     List[int] = field(default_factory=lambda: [0]*16)  # int8[16]

    def encode(self) -> bytes:
        motives = (list(self.motives) + [0]*16)[:16]
        body = struct.pack("<HHHHfHHIH",
            self.action      & 0xFFFF,
            self.guard       & 0xFFFF,
            self.str_index   & 0xFFFF,
            0,               # sentinel
            self.attenuation,
            self.autonomy    & 0xFFFF,
            self.num_attrs   & 0xFFFF,
            self.flags       & 0xFFFFFFFF,
            self.age_flags   & 0xFFFF,
        )
        body += struct.pack("<16b", *[max(-128, min(127, m)) for m in motives])
        # Pad to TTAB_ENTRY_SIZE (66 bytes)
        # body is now: 2+2+2+2+4+2+2+4+2+16 = 38 bytes, need 66 → pad 28
        body += bytes(TTAB_ENTRY_SIZE - len(body))
        assert len(body) == TTAB_ENTRY_SIZE, f"TTAB entry wrong size: {len(body)}"
        return body


@dataclass
class TTABResource:
    name:    str
    entries: List[TTABEntry] = field(default_factory=list)

    def add(self, action: int = 0, guard: int = 0, str_index: int = 0,
            autonomy: int = 0, flags: int = TTAB_FLAG_IS_AUTONOMOUS,
            age_flags: int = AGE_ALL, motives: List[int] = None) -> "TTABEntry":
        e = TTABEntry(action=action, guard=guard, str_index=str_index,
                      autonomy=autonomy, flags=flags, age_flags=age_flags,
                      motives=motives or [0]*16)
        self.entries.append(e)
        return e

    def encode(self) -> bytes:
        hdr = _name_hdr(self.name)
        hdr += struct.pack("<HH", TTAB_FORMAT, len(self.entries))
        return hdr + b"".join(e.encode() for e in self.entries)

    @classmethod
    def decode(cls, data: bytes, group_id: int, instance_id: int) -> "TTABResource":
        name, cur = _read_name(data)
        fmt, count = struct.unpack_from("<HH", data, cur); cur += 4
        res = cls(name=name)
        # Entry size depends on format; 0x000B = 66 bytes
        entry_size = TTAB_ENTRY_SIZE if fmt == TTAB_FORMAT else 66
        for _ in range(count):
            if cur + entry_size > len(data):
                break
            chunk = data[cur: cur + entry_size]
            action, guard, str_idx, sentinel, atten, autonomy, num_attrs, flags, age_flags = \
                struct.unpack_from("<HHHHfHHIH", chunk)
            motive_bytes = chunk[28:44]
            motives = list(struct.unpack("<16b", motive_bytes))
            res.entries.append(TTABEntry(
                action=action, guard=guard, str_index=str_idx,
                attenuation=atten, autonomy=autonomy, num_attrs=num_attrs,
                flags=flags, age_flags=age_flags, motives=motives,
            ))
            cur += entry_size
        return res


# ── CTSS ─────────────────────────────────────────────────────────────────────
#
# Catalog description string. Layout:
#   name_len  uint16
#   name      char[]
#   format    uint16  (0x0001)
#   count     uint16
#
# Per entry:
#   instance  uint16  matches OBJD instance
#   format    uint16  (0x0001)
#   lang      uint8   language ID
#   name      pstr    object name displayed in catalog
#   desc      pstr    object description displayed in catalog

CTSS_FORMAT = 0x0001


@dataclass
class CTSSEntry:
    instance:    int   = 0x0001   # which OBJD instance this describes
    language_id: int   = 1        # 1 = en-US
    obj_name:    str   = ""       # shown in catalog header
    description: str   = ""       # shown in catalog body

    def encode(self) -> bytes:
        return (struct.pack("<HHB", self.instance, CTSS_FORMAT, self.language_id) +
                _pstr(self.obj_name) + _pstr(self.description))


@dataclass
class CTSSResource:
    name:    str
    entries: List[CTSSEntry] = field(default_factory=list)

    def add(self, obj_name: str, description: str = "",
            instance: int = 0x0001, language: str = "en-us") -> None:
        from str_encoder import LANGUAGE_IDS
        self.entries.append(CTSSEntry(
            instance=instance,
            language_id=LANGUAGE_IDS.get(language.lower(), 1),
            obj_name=obj_name,
            description=description,
        ))

    def encode(self) -> bytes:
        hdr = _name_hdr(self.name)
        hdr += struct.pack("<HH", CTSS_FORMAT, len(self.entries))
        return hdr + b"".join(e.encode() for e in self.entries)

    @classmethod
    def decode(cls, data: bytes, group_id: int, instance_id: int) -> "CTSSResource":
        name, cur = _read_name(data)
        fmt, count = struct.unpack_from("<HH", data, cur); cur += 4
        res = cls(name=name)
        for _ in range(count):
            if cur + 5 > len(data):
                break
            inst, efmt, lang = struct.unpack_from("<HHB", data, cur); cur += 5
            obj_name, cur = _read_pstring(data, cur)
            desc, cur     = _read_pstring(data, cur)
            res.entries.append(CTSSEntry(inst, lang, obj_name, desc))
        return res


# ── BCON ─────────────────────────────────────────────────────────────────────
#
# Behaviour constant — a simple array of int16 values, accessed by index.
# Layout:
#   name_len  uint16
#   name      char[]
#   flag      uint8   (0 = enabled)
#   count     uint8   number of constants
#   values    int16[] the constants

@dataclass
class BCONResource:
    name:   str
    values: List[int] = field(default_factory=list)   # int16 each

    def add(self, value: int) -> None:
        self.values.append(value)

    def encode(self) -> bytes:
        hdr = _name_hdr(self.name)
        hdr += struct.pack("<BB", 0, len(self.values) & 0xFF)
        return hdr + struct.pack(f"<{len(self.values)}h", *self.values)

    @classmethod
    def decode(cls, data: bytes, group_id: int, instance_id: int) -> "BCONResource":
        name, cur = _read_name(data)
        if cur >= len(data):
            return cls(name=name)
        flag  = data[cur]; cur += 1
        count = data[cur]; cur += 1
        values = list(struct.unpack_from(f"<{count}h", data, cur))
        return cls(name=name, values=values)
