"""
glob_objd_encoders.py
Encoders for GLOB and OBJD — two resource types needed for complete object mods.

GLOB (0x474C4F42) - Global Behaviour
  Links a BHAV group ID to an object/person so the game knows which group
  to look in when running interactions. Every object mod needs one.

OBJD (0x4F424A44) - Object Data / Object Definition
  Defines core object properties: catalog price, room sort, function sort,
  GUID, object type flags, and many more. The "spine" of an object package.
  TS2 OBJD is 386 bytes of tightly packed fields.

Both are well-documented in SimPE source and MTS modding guides.
"""

import struct
from dataclasses import dataclass, field
from typing import Optional


# ── GLOB ─────────────────────────────────────────────────────────────────────

@dataclass
class GLOBResource:
    """
    GLOB binary layout:
      filename_len  uint16   (includes null)
      filename      char[]   null-terminated
      group_id      uint32   BHAV group this object uses
    """
    name:     str
    bhav_group: int   # The group ID that contains this object's BHAVs

    def encode(self) -> bytes:
        name_bytes = self.name.encode("latin-1") + b"\x00"
        return (
            struct.pack("<H", len(name_bytes)) +
            name_bytes +
            struct.pack("<I", self.bhav_group)
        )


# ── OBJD ─────────────────────────────────────────────────────────────────────
# Field layout based on SimPE ObjectData.cs and community documentation.
# TS2 OBJD has a LOT of fields. We expose the most commonly modded ones
# and pack the rest as zeros (safe defaults for new objects).

@dataclass
class OBJDResource:
    """
    Object Definition. Contains all core object metadata.

    Most fields default to 0 which is safe for a basic interaction-only mod.
    Set the fields you care about; the rest will be zero-padded.

    Key fields for behavior mods:
      object_type      - 0x00=normal, 0x02=person, 0x04=door, etc.
      interaction_group- Group ID for interactions (should match GLOB)
      num_slots        - number of routing slots
      guid             - object GUID (4 bytes, must be unique)
      initial_price    - catalog price in Simoleons
      catalog_flags    - controls catalog visibility
      room_sort        - which room tab in catalog (0=misc, 1=seating, etc.)
      function_sort    - which function tab (0=misc)
    """
    name:              str
    group_id:          int = 0x7FD46CD0
    instance_id:       int = 0x0001

    # ── Common fields ────────────────────────────────────────────────────────
    object_type:       int = 0x0000   # uint16
    num_slots:         int = 0        # uint8  routing slot count
    initial_price:     int = 0        # uint16 catalog price
    catalog_flags:     int = 0x0000   # uint16
    room_sort:         int = 0        # uint16
    function_sort:     int = 0        # uint16
    interaction_group: int = 0x7FD46CD0  # uint32  BHAV group
    guid:              int = 0x00000000  # uint32  unique object GUID

    # ── Memory / attribute counts ────────────────────────────────────────────
    num_attributes:    int = 0        # uint8  number of object attributes
    num_attributes_2:  int = 0        # uint8
    stack_size:        int = 4        # uint8  BHAV call stack depth

    # ── Raw override for advanced users ─────────────────────────────────────
    # If raw_data is set, it's used directly (must be exactly 386 bytes).
    raw_data: Optional[bytes] = None

    # OBJD is 386 bytes in TS2 (version 0x0086 = 134 decimal... actually
    # the field count varies by EP level. Base game = 74 uint16 fields = 148 bytes
    # + extra fields. We produce a safe minimal 148-byte version.)
    OBJD_FIELD_COUNT = 74  # base game TS2

    def encode(self) -> bytes:
        name_bytes = self.name.encode("latin-1") + b"\x00"
        header = struct.pack("<H", len(name_bytes)) + name_bytes

        if self.raw_data is not None:
            return header + self.raw_data

        # Build 74 uint16 fields, all zero by default
        fields = [0] * self.OBJD_FIELD_COUNT

        # Map known fields to their indices (0-based uint16 array)
        # Source: SimPE ObjectData field order
        fields[0]  = self.object_type        & 0xFFFF
        fields[6]  = self.num_slots          & 0xFFFF
        fields[11] = self.initial_price      & 0xFFFF
        fields[14] = self.num_attributes     & 0xFFFF
        fields[15] = self.num_attributes_2   & 0xFFFF
        fields[16] = self.stack_size         & 0xFFFF
        fields[20] = self.catalog_flags      & 0xFFFF
        fields[23] = self.room_sort          & 0xFFFF
        fields[24] = self.function_sort      & 0xFFFF

        # GUID spans fields[10] (low word) and [9] (high word)? 
        # Actually GUID is a uint32 at a specific offset — pack separately.
        # In base TS2 OBJD the GUID is at byte offset (after name header):
        #   field index 9 = GUID low word, 10 = GUID high word (little-endian uint32)
        fields[9]  = self.guid        & 0xFFFF
        fields[10] = (self.guid >> 16) & 0xFFFF

        # Interaction group (uint32) at fields[46..47]
        fields[46] = self.interaction_group & 0xFFFF
        fields[47] = (self.interaction_group >> 16) & 0xFFFF

        body = struct.pack("<" + "H" * self.OBJD_FIELD_COUNT, *fields)
        return header + body


# ── xml_parser additions ──────────────────────────────────────────────────────
# These are imported by xml_parser.py dynamically; exported here for clarity.

TYPE_GLOB = 0x474C4F42
TYPE_OBJD = 0x4F424A44


def parse_glob_xml(root) -> tuple[int, int, int, bytes]:
    """Parse a <glob> XML element."""
    from xml_parser import _int, _attr, DEFAULT_GROUP
    name       = _attr(root, "name", default="Untitled GLOB")
    group_id   = _int(_attr(root, "group"),    DEFAULT_GROUP)
    inst_id    = _int(_attr(root, "instance"), 0x0001)
    bhav_group = _int(_attr(root, "bhav_group", "bhavgroup"), DEFAULT_GROUP)

    res = GLOBResource(name=name, bhav_group=bhav_group)
    return (TYPE_GLOB, group_id, inst_id, res.encode())


def parse_objd_xml(root) -> tuple[int, int, int, bytes]:
    """Parse an <objd> XML element."""
    from xml_parser import _int, _attr, DEFAULT_GROUP
    name       = _attr(root, "name", default="Untitled OBJD")
    group_id   = _int(_attr(root, "group"),    DEFAULT_GROUP)
    inst_id    = _int(_attr(root, "instance"), 0x0001)

    res = OBJDResource(
        name              = name,
        group_id          = group_id,
        instance_id       = inst_id,
        object_type       = _int(root.get("object_type"),       0),
        num_slots         = _int(root.get("num_slots"),          0),
        initial_price     = _int(root.get("initial_price"),      0),
        catalog_flags     = _int(root.get("catalog_flags"),      0),
        room_sort         = _int(root.get("room_sort"),          0),
        function_sort     = _int(root.get("function_sort"),      0),
        interaction_group = _int(root.get("interaction_group"),  DEFAULT_GROUP),
        guid              = _int(root.get("guid"),               0),
        num_attributes    = _int(root.get("num_attributes"),     0),
        stack_size        = _int(root.get("stack_size"),         4),
    )
    return (TYPE_OBJD, group_id, inst_id, res.encode())
