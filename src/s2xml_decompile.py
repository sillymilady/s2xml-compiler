#!/usr/bin/env python3
"""
s2xml_decompile.py  —  Sims 2 .package → S2XML folder

Reads a .package file and writes each resource as a separate XML file
in an output directory. The XML is fully round-trip compatible with
s2xml_compile.py.

BHAVs are annotated with opcode names and operand descriptions.
Unknown resource types are written as raw hex blobs with a warning.

Usage:
  python s2xml_decompile.py MyMod.package
  python s2xml_decompile.py MyMod.package -o extracted/
  python s2xml_decompile.py MyMod.package --info
"""

import argparse
import sys
from pathlib import Path

from dbpf_reader    import read_package, RawResource, TYPE_NAMES
from xml_serializer import write_resource_xml


def decompile_package(pkg_path: Path, out_dir: Path, verbose: bool = True) -> bool:
    if verbose:
        print(f"\nDecompiling {pkg_path.name} → {out_dir}/\n")

    try:
        resources = read_package(str(pkg_path))
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return False

    if not resources:
        print("  (no resources found)")
        return True

    out_dir.mkdir(parents=True, exist_ok=True)
    counts  = {}
    success = True

    # Build BHAV map so TPRP serializer can split params/locals correctly
    from dbpf_reader import DecodedBHAV, TYPE_BHAV
    bhav_map = {r.instance_id: r for r in resources if isinstance(r, DecodedBHAV)}

    for res in resources:
        type_id   = res.type_id
        type_name = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
        raw_flag  = "  [unsupported — raw hex]" if isinstance(res, RawResource) else ""

        try:
            xml_path = write_resource_xml(res, out_dir, bhav_map=bhav_map)
            counts[type_name] = counts.get(type_name, 0) + 1
            if verbose:
                print(f"  → {xml_path.name:<52} [{type_name}]  inst=0x{res.instance_id:08X}{raw_flag}")
        except Exception as e:
            print(f"  [ERROR] {type_name} inst=0x{res.instance_id:08X}: {e}", file=sys.stderr)
            success = False

    if verbose:
        summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
        print(f"\n  ✓ {sum(counts.values())} resource(s) extracted  [{summary}]")
        print(f"  Output: {out_dir.resolve()}")

    return success


def list_package(pkg_path: Path) -> bool:
    try:
        resources = read_package(str(pkg_path))
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return False

    size_kb = pkg_path.stat().st_size / 1024
    print(f"\n{pkg_path.name}  ({size_kb:.1f} KB)  —  {len(resources)} resource(s)\n")

    for i, res in enumerate(resources):
        type_id   = res.type_id
        type_name = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
        name      = getattr(res, "name", "") or ""
        raw_note  = "  ← unsupported" if isinstance(res, RawResource) else ""
        data_size = len(res.data) if isinstance(res, RawResource) else "?"
        size_note = f"  ({data_size}b)" if isinstance(res, RawResource) else ""
        print(f"  [{i:2d}] {type_name:<6}  inst=0x{res.instance_id:08X}  "
              f"group=0x{res.group_id:08X}  '{name}'{size_note}{raw_note}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Decompile a Sims 2 .package into S2XML resource files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python s2xml_decompile.py MyMod.package
  python s2xml_decompile.py MyMod.package -o src/my_mod/
  python s2xml_decompile.py MyMod.package --info
""")
    parser.add_argument("package",         help=".package file to decompile")
    parser.add_argument("-o", "--output",  help="Output directory (default: <stem>/)")
    parser.add_argument("--info",          action="store_true",
                        help="List resources without writing files")
    parser.add_argument("-q", "--quiet",   action="store_true")

    args    = parser.parse_args()
    verbose = not args.quiet
    pkg     = Path(args.package)

    if not pkg.exists():
        print(f"[ERROR] Not found: {pkg}", file=sys.stderr)
        sys.exit(1)

    if args.info:
        sys.exit(0 if list_package(pkg) else 1)

    out_dir = Path(args.output) if args.output else pkg.parent / pkg.stem
    sys.exit(0 if decompile_package(pkg, out_dir, verbose) else 1)


if __name__ == "__main__":
    main()
