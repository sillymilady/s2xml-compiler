"""
nref_vers_encoders.py
Simple encoders for remaining common TS2 resource types:

  NREF  0x4E524546  Name Reference - links a name string to a resource
  TTAs  0x54544173  Pie Menu Strings - text strings for TTAB interactions  
  CATS  0x43415453  Catalog Strings - additional catalog text
  VERS  0x56455253  Version - simple version number resource
  PIFF  0x50494646  Package Index - auto-generated, passthrough only
"""

import struct
from dataclasses import dataclass, field
from typing import List

TYPE_NREF = 0x4E524546
TYPE_TTAs = 0x54544173
TYPE_CATS = 0x43415453
TYPE_VERS = 0x56455253
TYPE_PIFF = 0x50494646


def _pstr(s: str) -> bytes:
    b = s.encode("latin-1", errors="replace")[:255]
    return bytes([len(b)]) + b

def _name_hdr(name: str) -> bytes:
    nb = name.encode("latin-1") + b"\x00"
    return struct.pack("<H", len(nb)) + nb


# ── NREF ─────────────────────────────────────────────────────────────────────

@dataclass
class NREFResource:
    """
    Name Reference - associates a string name with a resource group.
    Layout: name_len(2) | name | filename_len(2) | filename
    """
    name:     str
    filename: str = ""   # the referenced resource name

    def encode(self) -> bytes:
        nl, nb = _name_hdr(self.name)
        fn_bytes = self.filename.encode("latin-1") + b"\x00"
        fn_len   = struct.pack("<H", len(fn_bytes))
        return nl + nb + fn_len + fn_bytes

    @classmethod
    def decode(cls, data: bytes) -> "NREFResource":
        nl = struct.unpack_from("<H", data, 0)[0]
        name = data[2:2+nl-1].decode("latin-1", errors="replace")
        cur = 2 + nl
        if cur + 2 <= len(data):
            fl = struct.unpack_from("<H", data, cur)[0]
            filename = data[cur+2:cur+2+fl-1].decode("latin-1", errors="replace")
        else:
            filename = ""
        return cls(name=name, filename=filename)


# ── TTAs ─────────────────────────────────────────────────────────────────────

@dataclass 
class TTAsResource:
    """
    Pie Menu Strings - same format as STR# but different type ID.
    Used alongside TTAB for interaction text.
    """
    name:    str
    entries: List = field(default_factory=list)

    def encode(self) -> bytes:
        from str_encoder import STRResource
        # Re-use STR encoder, just different type ID
        sr = STRResource(name=self.name)
        sr.entries = self.entries
        # Get the encoded bytes (strip the type difference)
        return sr.encode()

    @classmethod
    def decode(cls, data: bytes) -> "TTAsResource":
        from dbpf_reader import _decode_str
        # Re-use STR decoder
        decoded = _decode_str(data, 0, 0)
        res = cls(name=decoded.name)
        res.entries = decoded.entries
        return res


# ── CATS ─────────────────────────────────────────────────────────────────────

@dataclass
class CATSResource:
    """
    Catalog Strings - additional catalog description entries.
    Same format as STR#.
    """
    name:    str
    entries: List = field(default_factory=list)

    def encode(self) -> bytes:
        from str_encoder import STRResource
        sr = STRResource(name=self.name)
        sr.entries = self.entries
        return sr.encode()


# ── VERS ─────────────────────────────────────────────────────────────────────

@dataclass
class VERSResource:
    """
    Version resource - simple string.
    Layout: name_len(2) | name | version_string(pstr)
    """
    name:    str
    version: str = "1.0"

    def encode(self) -> bytes:
        nl, nb = _name_hdr(self.name)
        return nl + nb + _pstr(self.version)

    @classmethod
    def decode(cls, data: bytes) -> "VERSResource":
        nl = struct.unpack_from("<H", data, 0)[0]
        name = data[2:2+nl-1].decode("latin-1", errors="replace")
        cur = 2 + nl
        if cur < len(data):
            vl = data[cur]
            version = data[cur+1:cur+1+vl].decode("latin-1", errors="replace")
        else:
            version = "1.0"
        return cls(name=name, version=version)
