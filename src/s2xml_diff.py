#!/usr/bin/env python3
"""
s2xml_diff.py  —  Compare two Sims 2 .package files

Shows which resources were added, removed, or changed between two packages.
For changed BHAVs, shows a detailed instruction-level diff.

Usage:
  python s2xml_diff.py original.package modified.package
  python s2xml_diff.py original.package modified.package --brief
  python s2xml_diff.py original.package modified.package --bhav-only
"""

import argparse
import struct
import sys
from pathlib import Path

from dbpf_reader import read_package, TYPE_NAMES, RawResource


def _resource_key(res) -> tuple:
    return (res.type_id, res.group_id, res.instance_id)


def _resource_label(res) -> str:
    tname = TYPE_NAMES.get(res.type_id, f"0x{res.type_id:08X}")
    name  = getattr(res, "name", "") or ""
    return f"{tname:<6} inst=0x{res.instance_id:08X}  '{name}'"


def _raw_data(res) -> bytes:
    """Get the raw binary data for a resource (re-encode decoded resources)."""
    if isinstance(res, RawResource):
        return res.data
    # Re-encode by importing the appropriate encoder
    from dbpf_reader import (
        DecodedBHAV, DecodedSTR, DecodedTPRP, DecodedTRCN, DecodedOBJf,
        TYPE_BHAV, TYPE_STR, TYPE_TPRP, TYPE_TRCN, TYPE_OBJf,
    )
    from xml_serializer import serialize_resource
    from xml_parser import parse_resource_xml
    import tempfile, os
    # Use the serializer → parser route for a byte-accurate re-encode
    xml_str = serialize_resource(res)
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(xml_str)
        fname = f.name
    try:
        _, _, _, data = parse_resource_xml(fname)
        return data
    except Exception:
        return b""
    finally:
        os.unlink(fname)


def _diff_bhav_instructions(a_res, b_res) -> list[str]:
    """Return line-level diff of two decoded BHAVs' instruction lists."""
    from dbpf_reader import DecodedBHAV, GOTO_NAMES
    import opcodes as op_ref

    if not isinstance(a_res, DecodedBHAV) or not isinstance(b_res, DecodedBHAV):
        return []

    lines = []
    a_instrs = a_res.instructions
    b_instrs = b_res.instructions

    max_len = max(len(a_instrs), len(b_instrs))

    for i in range(max_len):
        a = a_instrs[i] if i < len(a_instrs) else None
        b = b_instrs[i] if i < len(b_instrs) else None

        def fmt_instr(instr):
            if instr is None:
                return "(none)"
            gt = GOTO_NAMES.get(instr.goto_true,  str(instr.goto_true))
            gf = GOTO_NAMES.get(instr.goto_false, str(instr.goto_false))
            ops = " ".join(f"{v:02X}" for v in instr.operands)
            name = op_ref.name(instr.opcode)
            return f"0x{instr.opcode:04X} ({name:<32}) t={gt:<5} f={gf:<5} ops=[{ops}]"

        fa, fb = fmt_instr(a), fmt_instr(b)
        if fa == fb:
            lines.append(f"    [{i:3d}] = {fa}")
        elif a is None:
            lines.append(f"    [{i:3d}] + {fb}")
        elif b is None:
            lines.append(f"    [{i:3d}] - {fa}")
        else:
            lines.append(f"    [{i:3d}] - {fa}")
            lines.append(f"    [{i:3d}] + {fb}")

    return lines


def diff_packages(path_a: Path, path_b: Path,
                  brief: bool = False, bhav_only: bool = False) -> int:
    """
    Diff two packages. Returns exit code: 0=identical, 1=different, 2=error.
    """
    try:
        resources_a = read_package(str(path_a))
        resources_b = read_package(str(path_b))
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    # Build key → resource maps
    map_a = {_resource_key(r): r for r in resources_a}
    map_b = {_resource_key(r): r for r in resources_b}

    keys_a = set(map_a)
    keys_b = set(map_b)

    added   = sorted(keys_b - keys_a)
    removed = sorted(keys_a - keys_b)
    common  = sorted(keys_a & keys_b)

    TYPE_BHAV = 0x42484156

    # Filter to BHAV-only if requested
    if bhav_only:
        added   = [k for k in added   if k[0] == TYPE_BHAV]
        removed = [k for k in removed if k[0] == TYPE_BHAV]
        common  = [k for k in common  if k[0] == TYPE_BHAV]

    changed = []
    for key in common:
        da = _raw_data(map_a[key])
        db = _raw_data(map_b[key])
        if da != db:
            changed.append(key)

    identical = not (added or removed or changed)

    print(f"\nDiff: {path_a.name}  vs  {path_b.name}")
    print(f"  A: {len(resources_a)} resources    B: {len(resources_b)} resources\n")

    if identical:
        print("  ✓ Packages are identical (all resource data matches)\n")
        return 0

    # Summary counts
    print(f"  + {len(added)} added    - {len(removed)} removed    ~ {len(changed)} changed\n")

    for key in removed:
        res = map_a[key]
        print(f"  - {_resource_label(res)}")

    for key in added:
        res = map_b[key]
        print(f"  + {_resource_label(res)}")

    for key in changed:
        res_a = map_a[key]
        res_b = map_b[key]
        tname = TYPE_NAMES.get(key[0], f"0x{key[0]:08X}")
        print(f"  ~ {_resource_label(res_a)}")

        if not brief and key[0] == TYPE_BHAV:
            diff_lines = _diff_bhav_instructions(res_a, res_b)
            has_changes = any(l.strip().startswith(("+", "-")) for l in diff_lines)
            if has_changes:
                # Show only changed lines ± context
                changed_idx = {i for i, l in enumerate(diff_lines) if l.strip().startswith(("+", "-"))}
                context = set()
                for ci in changed_idx:
                    for offset in range(-2, 3):
                        context.add(ci + offset)
                prev_printed = -1
                for i, line in enumerate(diff_lines):
                    if i in context:
                        if i > prev_printed + 1:
                            print("         ...")
                        print(line)
                        prev_printed = i
                if prev_printed < len(diff_lines) - 1:
                    print("         ...")
        elif not brief:
            # Show raw byte diff summary for non-BHAV types
            da = _raw_data(res_a)
            db = _raw_data(res_b)
            print(f"       size: {len(da)}b → {len(db)}b  ({len(db)-len(da):+d} bytes)")
            first_diff = next((i for i, (a, b) in enumerate(zip(da, db)) if a != b),
                              min(len(da), len(db)))
            print(f"       first difference at byte offset {first_diff}")

    print()
    return 1


def main():
    parser = argparse.ArgumentParser(
        description="Diff two Sims 2 .package files",
        epilog="""
Examples:
  python s2xml_diff.py v1.package v2.package
  python s2xml_diff.py v1.package v2.package --brief
  python s2xml_diff.py v1.package v2.package --bhav-only
""")
    parser.add_argument("package_a", help="Original .package")
    parser.add_argument("package_b", help="Modified .package")
    parser.add_argument("--brief",     action="store_true",
                        help="Show only added/removed/changed list, no detail")
    parser.add_argument("--bhav-only", action="store_true",
                        help="Only compare BHAV resources")

    args = parser.parse_args()
    a, b = Path(args.package_a), Path(args.package_b)

    for p in (a, b):
        if not p.exists():
            print(f"[ERROR] Not found: {p}", file=sys.stderr)
            sys.exit(2)

    code = diff_packages(a, b, brief=args.brief, bhav_only=args.bhav_only)
    sys.exit(code)


if __name__ == "__main__":
    main()
