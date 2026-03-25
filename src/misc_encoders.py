"""
misc_encoders.py
Encoders for TPRP, TRCN, and OBJf resource types.

All share the same name header convention:
  uint16  name_len    (includes null terminator)
  char[]  name        (null-terminated)
  ...rest of fields
"""

import struct
from dataclasses import dataclass, field
from typing import List


def _pstr(s: str) -> bytes:
    b = s.encode("latin-1", errors="replace")[:255]
    return bytes([len(b)]) + b

def _name_header(name: str) -> tuple[bytes, bytes]:
    """Returns (name_len_bytes, name_bytes) — write them in order."""
    nb = name.encode("latin-1") + b"\x00"
    return struct.pack("<H", len(nb)), nb


# ── TPRP ─────────────────────────────────────────────────────────────────────

@dataclass
class TPRPEntry:
    name:  str
    label: str = ""


@dataclass
class TPRPResource:
    """
    Layout: name_len | name | format(uint16=0x0002) | count(uint16) | entries
    Each entry: pstr name + pstr label
    """
    bhav_name: str
    params:    List[TPRPEntry] = field(default_factory=list)
    locals_:   List[TPRPEntry] = field(default_factory=list)

    def encode(self) -> bytes:
        nl, nb = _name_header(self.bhav_name)
        entries = self.params + self.locals_
        header = struct.pack("<HH", 0x0002, len(entries))
        body = b"".join(_pstr(e.name) + _pstr(e.label) for e in entries)
        return nl + nb + header + body


# ── TRCN ─────────────────────────────────────────────────────────────────────

@dataclass
class TRCNEntry:
    name:        str
    value:       int   # int16 signed
    description: str = ""


@dataclass
class TRCNResource:
    """
    Layout: name_len | name | format(uint16=0x0000) | count(uint16) | entries
    Each entry: flag(uint8=1) | value(int16) | pstr name | pstr desc
    """
    name:    str
    entries: List[TRCNEntry] = field(default_factory=list)

    def encode(self) -> bytes:
        nl, nb = _name_header(self.name)
        header = struct.pack("<HH", 0x0000, len(self.entries))
        body = bytearray()
        for e in self.entries:
            body += struct.pack("<Bh", 1, e.value)
            body += _pstr(e.name)
            body += _pstr(e.description)
        return nl + nb + header + bytes(body)


# ── OBJf ─────────────────────────────────────────────────────────────────────

@dataclass
class OBJfEntry:
    action_bhav: int
    guard_bhav:  int


@dataclass
class OBJfResource:
    """
    Layout: name_len | name | format(uint16=0x0001) | count(uint16) | entries
    Each entry: action_bhav(uint32) | guard_bhav(uint32)
    """
    name:    str
    entries: List[OBJfEntry] = field(default_factory=list)

    def add(self, action_bhav: int, guard_bhav: int = 0):
        self.entries.append(OBJfEntry(action_bhav, guard_bhav))

    def encode(self) -> bytes:
        nl, nb = _name_header(self.name)
        header = struct.pack("<HH", 0x0001, len(self.entries))
        body = b"".join(struct.pack("<II", e.action_bhav, e.guard_bhav) for e in self.entries)
        return nl + nb + header + body
