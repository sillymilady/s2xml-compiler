"""
dbpf_writer.py
Low-level DBPF 1.1 package writer (Sims 2 format).
Produces byte-for-byte correct .package files readable by SimPE.
"""

import struct
from dataclasses import dataclass, field
from typing import List, Tuple


# ---------------------------------------------------------------------------
# DBPF constants
# ---------------------------------------------------------------------------
DBPF_MAGIC       = b"DBPF"
MAJOR_VERSION    = 1
MINOR_VERSION    = 1
HOLE_INDEX_TYPE  = 0xE86B1EEF  # "hole" entry type used in index


@dataclass
class IndexEntry:
    type_id:    int   # uint32
    group_id:   int   # uint32
    instance_id: int  # uint32
    data:       bytes


class DBPFWriter:
    """
    Builds a DBPF 1.1 package from a list of (type_id, group_id, instance_id, data) tuples.
    Call add_resource() for each resource, then write_package() to get bytes.
    """

    def __init__(self):
        self.entries: List[IndexEntry] = []

    def add_resource(self, type_id: int, group_id: int, instance_id: int, data: bytes):
        self.entries.append(IndexEntry(type_id, group_id, instance_id, data))

    # ------------------------------------------------------------------
    # DBPF header layout (96 bytes)
    # Offsets match the Maxis spec and SimPE expectations exactly.
    # ------------------------------------------------------------------
    HEADER_SIZE = 96

    def _build_header(self, index_offset: int, index_size: int, index_count: int) -> bytes:
        h = bytearray(self.HEADER_SIZE)
        struct.pack_into("<4s", h, 0, DBPF_MAGIC)
        struct.pack_into("<I", h, 4,  MAJOR_VERSION)
        struct.pack_into("<I", h, 8,  MINOR_VERSION)
        # bytes 12-35: reserved zeros
        struct.pack_into("<I", h, 36, 0)  # date created
        struct.pack_into("<I", h, 40, 0)  # date modified
        struct.pack_into("<I", h, 44, 1)  # index major version = 7 → stored as 1
        struct.pack_into("<I", h, 48, index_count)
        struct.pack_into("<I", h, 52, index_offset)
        struct.pack_into("<I", h, 56, index_size)
        struct.pack_into("<I", h, 60, 0)  # hole index entry count
        struct.pack_into("<I", h, 64, 0)  # hole index offset
        struct.pack_into("<I", h, 68, 0)  # hole index size
        struct.pack_into("<I", h, 72, 7)  # index minor version
        # bytes 76-95: reserved zeros
        return bytes(h)

    def write_package(self) -> bytes:
        """Return the complete .package file as bytes."""
        # 1. Lay out resource data sequentially after the header
        data_blob = bytearray()
        offsets: List[int] = []

        for entry in self.entries:
            offsets.append(self.HEADER_SIZE + len(data_blob))
            data_blob += entry.data

        # 2. Build index (20 bytes per entry: type, group, instance, offset, size)
        index_offset = self.HEADER_SIZE + len(data_blob)
        index_blob = bytearray()
        for i, entry in enumerate(self.entries):
            index_blob += struct.pack("<IIIII",
                entry.type_id,
                entry.group_id,
                entry.instance_id,
                offsets[i],
                len(entry.data))

        # 3. Build header
        header = self._build_header(index_offset, len(index_blob), len(self.entries))

        return header + bytes(data_blob) + bytes(index_blob)
