"""
str_encoder.py
Encodes STR# (String Table) resources into the Sims 2 binary format.

Layout:
  uint16  name_len        includes null terminator
  char[]  name            null-terminated
  uint16  format          0x0042
  uint16  count           total string entries

  Per entry:
  uint8   language_id
  pstr    value           uint8 length + chars (no null)
  pstr    description

Language IDs:
  0=default  1=en-US  2=en-UK  3=French  4=German  5=Italian
  6=Spanish  7=Dutch  8=Danish  9=Swedish  10=Norwegian  11=Finnish
  12=Hebrew  13=Russian  14=Portuguese  15=Japanese  16=Polish
  17=Simplified Chinese  18=Traditional Chinese  19=Thai  20=Korean
"""

import struct
from dataclasses import dataclass, field
from typing import List

STR_FORMAT = 0x0042

LANGUAGE_IDS = {
    "default": 0, "en-us": 1, "en-uk": 2, "french": 3, "german": 4,
    "italian": 5, "spanish": 6, "dutch": 7, "danish": 8, "swedish": 9,
    "norwegian": 10, "finnish": 11, "hebrew": 12, "russian": 13,
    "portuguese": 14, "japanese": 15, "polish": 16,
    "zh-simple": 17, "zh-trad": 18, "thai": 19, "korean": 20,
}


def _pascal_str(s: str) -> bytes:
    encoded = s.encode("latin-1", errors="replace")[:255]
    return bytes([len(encoded)]) + encoded


@dataclass
class STREntry:
    value:       str
    description: str = ""
    language_id: int = 1

    def encode(self) -> bytes:
        return bytes([self.language_id]) + _pascal_str(self.value) + _pascal_str(self.description)


@dataclass
class STRResource:
    name:    str
    entries: List[STREntry] = field(default_factory=list)

    def add(self, value: str, description: str = "", language: str = "en-us"):
        lang_id = LANGUAGE_IDS.get(language.lower(), 1)
        self.entries.append(STREntry(value, description, lang_id))

    def encode(self) -> bytes:
        name_bytes = self.name.encode("latin-1") + b"\x00"
        name_len = struct.pack("<H", len(name_bytes))
        header = struct.pack("<HH", STR_FORMAT, len(self.entries))
        body = b"".join(e.encode() for e in self.entries)
        return name_len + name_bytes + header + body
