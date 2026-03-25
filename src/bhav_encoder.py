"""
bhav_encoder.py
Encodes BHAV (Behaviour) resources into the binary format used by The Sims 2.

BHAV binary layout (SimPE / Maxis spec, format 0x8008):
  uint16  name_len        length of name string INCLUDING null terminator
  char[]  name            null-terminated name string
  uint16  format          0x8008 for TS2
  uint16  count           number of instructions
  uint8   tree_type       0=global, 1=person, 2=autonomous, 4=notavail, 5=stategraph
  uint8   argc            parameter count
  uint8   locals          local variable count
  uint8   flags           0x01 = cache bhav
  int32   tree_version    usually 0

  Per instruction (14 bytes for format 0x8008):
  uint16  opcode
  uint8   goto_true       0xFD=exit true, 0xFE=exit false, 0xFF=error, else node index
  uint8   goto_false
  uint8   node_version    0xFE = current
  uint8   pad             always 0
  uint8[8] operands
"""

import struct
from dataclasses import dataclass, field
from typing import List


BHAV_FORMAT = 0x8008
EXIT_TRUE   = 0xFD   # 253
EXIT_FALSE  = 0xFE   # 254
EXIT_ERROR  = 0xFF   # 255


@dataclass
class BHAVInstruction:
    opcode:       int
    goto_true:    int = EXIT_TRUE
    goto_false:   int = EXIT_FALSE
    node_version: int = 0xFE
    operands:     List[int] = field(default_factory=lambda: [0] * 8)
    comment:      str = ""   # user annotation — not encoded in binary, survives XML round-trip

    def encode(self) -> bytes:
        ops = (list(self.operands) + [0] * 8)[:8]
        return struct.pack("<HBBBB",
            self.opcode,
            self.goto_true   & 0xFF,
            self.goto_false  & 0xFF,
            self.node_version & 0xFF,
            0,  # pad
        ) + bytes(ops)
        # 2 + 1 + 1 + 1 + 1 + 8 = 14 bytes


@dataclass
class BHAVResource:
    name:         str
    instructions: List[BHAVInstruction] = field(default_factory=list)
    tree_type:    int = 0
    argc:         int = 0
    locals:       int = 0
    flags:        int = 0x01
    tree_version: int = 0

    def encode(self) -> bytes:
        name_bytes = self.name.encode("latin-1") + b"\x00"
        # Correct layout: name_len(2) | name(n) | format(2) | count(2) | type(1) | argc(1) | locals(1) | flags(1) | tree_ver(4)
        name_len = struct.pack("<H", len(name_bytes))
        header = struct.pack("<HHBBBBi",
            BHAV_FORMAT,
            len(self.instructions),
            self.tree_type & 0xFF,
            self.argc      & 0xFF,
            self.locals    & 0xFF,
            self.flags     & 0xFF,
            self.tree_version,
        )
        body = b"".join(i.encode() for i in self.instructions)
        return name_len + name_bytes + header + body
