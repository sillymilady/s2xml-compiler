#!/usr/bin/env python3
"""
s2xml_compile.py  —  S2XML → Sims 2 .package compiler

Each XML file = one resource (BHAV, STR#, TPRP, TRCN, OBJf, GLOB, OBJD)
All XMLs given → one .package file containing all those resources.

Usage:
  python s2xml_compile.py my_mod/                     # all XMLs in folder
  python s2xml_compile.py my_mod/ -o dist/Mod.package # explicit output
  python s2xml_compile.py a.xml b.xml c.xml           # specific files
  python s2xml_compile.py my_mod/ --lint-only         # validate without writing
"""

import argparse
import sys
from pathlib import Path

from xml_parser  import parse_resource_xml, TYPE_NAMES
from dbpf_writer import DBPFWriter
from linter      import lint_resources, print_lint_report

RESOURCE_EXTS = {".xml"}


def collect_xml_files(paths: list[Path]) -> list[Path]:
    result = []
    for p in paths:
        if p.is_dir():
            found = sorted(p.glob("*.xml"))
            if not found:
                print(f"  [warn] No .xml files in directory: {p}")
            result.extend(found)
        elif p.suffix.lower() in RESOURCE_EXTS:
            result.append(p)
        else:
            print(f"  [warn] Skipping non-XML file: {p}")
    return result


def compile_package(xml_files: list[Path], out_path: Path,
                    verbose: bool = True, lint_only: bool = False) -> bool:
    if not xml_files:
        print("[ERROR] No XML files to compile.", file=sys.stderr)
        return False

    resources  = []
    file_names = []
    success    = True
    counts     = {}

    # ── Two-pass compile: collect constants from TRCN/BCON first ────────────
    from xml_parser import set_global_constants
    import xml.etree.ElementTree as _ET

    global_consts = {}
    for xml_path in xml_files:
        try:
            root = _ET.parse(str(xml_path)).getroot()
        except Exception:
            continue
        tag = root.tag.lower()
        if tag == "trcn":
            for c in root.findall("constant"):
                cname = c.get("name", "")
                cval  = c.get("value", "0")
                try:
                    if cname:
                        global_consts[cname] = int(cval, 0)
                except ValueError:
                    pass
        elif tag == "bcon":
            res_name = root.get("name", xml_path.stem)
            for i, c in enumerate(root.findall("constant")):
                cval = c.get("value", "0")
                try:
                    global_consts[f"{res_name}[{i}]"] = int(cval, 0)
                except ValueError:
                    pass

    if global_consts and verbose:
        print(f"  [constants] {len(global_consts)} named constant(s) available for $CONST refs")
    set_global_constants(global_consts)

    # ── Parse all XML files ──────────────────────────────────────────────────
    for xml_path in xml_files:
        try:
            entry = parse_resource_xml(str(xml_path))
        except ValueError as e:
            print(f"  [ERROR] {xml_path.name}: {e}", file=sys.stderr)
            success = False
            continue

        type_id, group_id, inst_id, data = entry
        resources.append(entry)
        file_names.append(xml_path.name)
        type_name = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
        counts[type_name] = counts.get(type_name, 0) + 1

        if verbose:
            print(f"  + {xml_path.name:<42} [{type_name}]  group=0x{group_id:08X}  inst=0x{inst_id:08X}")

    if not resources:
        print("[ERROR] No resources compiled successfully.", file=sys.stderr)
        return False

    # ── Lint ─────────────────────────────────────────────────────────────────
    if verbose:
        print()
    lint_msgs = lint_resources(resources, file_names)
    error_count, warn_count = print_lint_report(lint_msgs, verbose)

    if error_count > 0:
        print(f"\n  [BLOCKED] Fix {error_count} error(s) before compiling.", file=sys.stderr)
        return False

    if lint_only:
        summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
        print(f"\n  ✓ Lint OK — {len(resources)} resource(s)  [{summary}]  {warn_count} warning(s)")
        return True

    # ── Write package ─────────────────────────────────────────────────────────
    writer = DBPFWriter()
    for type_id, group_id, inst_id, data in resources:
        writer.add_resource(type_id, group_id, inst_id, data)

    pkg_bytes = writer.write_package()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(pkg_bytes)

    if verbose:
        summary = "  ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
        kb = len(pkg_bytes) / 1024
        status = "✓" if success else "⚠ (with errors)"
        print(f"\n  {status}  {out_path}  [{summary}]  {kb:.1f} KB")

    return success


def default_output_name(inputs: list[Path]) -> Path:
    if len(inputs) == 1 and inputs[0].is_dir():
        return inputs[0].parent / (inputs[0].name + ".package")
    parents = {p.parent for p in inputs if p.is_file()}
    if len(parents) == 1:
        folder = parents.pop()
        if folder != Path("."):
            return folder / (folder.name + ".package")
    first = next((p for p in inputs if p.suffix.lower() == ".xml"), inputs[0])
    return first.with_suffix(".package")


def main():
    parser = argparse.ArgumentParser(
        description="Compile S2XML resource files into a Sims 2 .package",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Each .xml file = one resource. All files → one combined .package.

Examples:
  python s2xml_compile.py my_mod/
  python s2xml_compile.py my_mod/ -o dist/MyMod.package
  python s2xml_compile.py a.bhav.xml b.str.xml -o MyMod.package
  python s2xml_compile.py my_mod/ --lint-only
""")
    parser.add_argument("inputs", nargs="+", help="XML files and/or folders")
    parser.add_argument("-o", "--output",    help="Output .package path")
    parser.add_argument("--lint-only",       action="store_true",
                        help="Validate without writing a package")
    parser.add_argument("-q", "--quiet",     action="store_true")
    parser.add_argument("-w", "--watch",     action="store_true",
                        help="Watch for file changes and auto-recompile")

    args    = parser.parse_args()
    verbose = not args.quiet

    input_paths = [Path(p) for p in args.inputs]
    missing = [p for p in input_paths if not p.exists()]
    if missing:
        for m in missing:
            print(f"[ERROR] Not found: {m}", file=sys.stderr)
        sys.exit(1)

    xml_files = collect_xml_files(input_paths)
    if not xml_files:
        print("[ERROR] No XML files found.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.output) if args.output else default_output_name(input_paths)

    if verbose:
        mode = "Linting" if args.lint_only else "Compiling"
        print(f"\n{mode} {len(xml_files)} resource(s)" +
              (f" → {out_path}" if not args.lint_only else "") + "\n")

    if args.watch:
        watch_mode(input_paths, out_path, verbose)
        sys.exit(0)

    ok = compile_package(xml_files, out_path, verbose, lint_only=args.lint_only)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()


def watch_mode(input_paths: list[Path], out_path: Path, verbose: bool = True):
    """
    Watch input files/directories for changes and auto-recompile.
    Polls every second. Press Ctrl+C to stop.
    """
    import time

    print(f"\nWatch mode — monitoring {len(input_paths)} path(s) for changes.")
    print("Press Ctrl+C to stop.\n")

    def get_mtimes(paths):
        mtimes = {}
        for p in paths:
            if p.is_dir():
                for f in p.glob("*.xml"):
                    try:
                        mtimes[str(f)] = f.stat().st_mtime
                    except OSError:
                        pass
            elif p.exists():
                try:
                    mtimes[str(p)] = p.stat().st_mtime
                except OSError:
                    pass
        return mtimes

    last_mtimes = {}
    last_result = None

    try:
        while True:
            current_mtimes = get_mtimes(input_paths)

            changed = set(current_mtimes) - set(last_mtimes)
            changed |= {k for k, v in current_mtimes.items()
                        if last_mtimes.get(k) != v}
            removed = set(last_mtimes) - set(current_mtimes)

            if changed or removed or last_result is None:
                if changed:
                    for c in sorted(changed):
                        print(f"  ↺  Changed: {Path(c).name}")
                if removed:
                    for r in sorted(removed):
                        print(f"  ✗  Removed: {Path(r).name}")

                xml_files = collect_xml_files(input_paths)
                if xml_files:
                    from datetime import datetime
                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"\n[{ts}] Recompiling {len(xml_files)} file(s)...")
                    compile_package(xml_files, out_path, verbose=False)
                    # Print compact result
                    if out_path.exists():
                        kb = out_path.stat().st_size / 1024
                        print(f"[{ts}] ✓  {out_path.name}  ({kb:.1f} KB)\n")
                else:
                    print("  [warn] No XML files found\n")

                last_mtimes = current_mtimes
                last_result = True

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nWatch mode stopped.")
