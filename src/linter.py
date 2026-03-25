"""
linter.py
Pre-compile and post-decode validation for S2XML mod resources.

Checks performed:
  - Duplicate (type, group, instance) tuples within a package
  - BHAV instructions with out-of-range goto targets
  - OBJf slots referencing BHAV instances not present in the package
  - STR# instance collisions (two string tables at same instance)
  - TPRP instances that don't match any BHAV
  - Empty BHAVs (zero instructions)
  - Operand bytes out of uint8 range

Returns a list of LintMessage objects. Errors block compile; warnings don't.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class LintMessage:
    level:    str    # "error" | "warning" | "info"
    resource: str    # human-readable resource label
    message:  str

    def __str__(self):
        icon = {"error": "✗", "warning": "⚠", "info": "ℹ"}.get(self.level, "?")
        return f"  {icon} [{self.level.upper()}] {self.resource}: {self.message}"


def _label(type_id: int, name: str, inst: int) -> str:
    from dbpf_reader import TYPE_NAMES
    tname = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
    return f"{tname} '{name}' (inst=0x{inst:08X})"


def lint_resources(resources: list[tuple[int, int, int, bytes]], source_names: list[str] = None) -> list[LintMessage]:
    """
    Lint a list of (type_id, group_id, instance_id, data) tuples.
    source_names: optional parallel list of filenames for better error messages.
    Returns list of LintMessage.
    """
    from dbpf_reader import (
        TYPE_BHAV, TYPE_STR, TYPE_TPRP, TYPE_TRCN, TYPE_OBJf,
        TYPE_GLOB, TYPE_OBJD,
        _decode_bhav, _decode_str, _decode_tprp, _decode_trcn, _decode_objf,
        EXIT_TRUE, EXIT_FALSE, EXIT_ERROR,
    )

    msgs = []
    seen_keys: dict[tuple, str] = {}   # (type, group, inst) → source name

    decoded_bhavs:  dict[int, Any] = {}   # inst → DecodedBHAV
    decoded_objfs:  list[Any] = []
    decoded_tprps:  list[Any] = []
    objf_sources:   list[str] = []

    names = source_names or [f"resource[{i}]" for i in range(len(resources))]

    # ── Pass 1: decode everything and check for duplicate keys ───────────────
    for i, (type_id, group_id, inst_id, data) in enumerate(resources):
        src = names[i]
        key = (type_id, group_id, inst_id)

        if key in seen_keys:
            from dbpf_reader import TYPE_NAMES
            tname = TYPE_NAMES.get(type_id, f"0x{type_id:08X}")
            msgs.append(LintMessage(
                "error", src,
                f"Duplicate resource: {tname} group=0x{group_id:08X} inst=0x{inst_id:08X} "
                f"already defined in {seen_keys[key]}",
            ))
        seen_keys[key] = src

        # Decode for further checks
        try:
            if type_id == TYPE_BHAV:
                d = _decode_bhav(data, group_id, inst_id)
                decoded_bhavs[inst_id] = d
            elif type_id == TYPE_STR:
                pass  # no deep STR linting needed beyond duplicates
            elif type_id == TYPE_TPRP:
                d = _decode_tprp(data, group_id, inst_id)
                decoded_tprps.append((d, src))
            elif type_id == TYPE_OBJD:
                pass
            elif type_id == TYPE_OBJf:
                d = _decode_objf(data, group_id, inst_id)
                decoded_objfs.append(d)
                objf_sources.append(src)
        except Exception as e:
            msgs.append(LintMessage("warning", src, f"Could not decode for linting: {e}"))

    all_bhav_insts = set(decoded_bhavs.keys())

    # ── Pass 2: BHAV instruction validation ──────────────────────────────────
    EXITS = {EXIT_TRUE, EXIT_FALSE, EXIT_ERROR}

    for inst_id, bhav in decoded_bhavs.items():
        src = names[list(decoded_bhavs.keys()).index(inst_id)] if source_names else f"BHAV 0x{inst_id:08X}"
        label = f"BHAV '{bhav.name}' (inst=0x{inst_id:08X})"
        n = len(bhav.instructions)

        if n == 0:
            msgs.append(LintMessage("warning", label, "BHAV has zero instructions — it will do nothing"))
            continue

        for j, instr in enumerate(bhav.instructions):
            for goto_name, goto_val in [("true", instr.goto_true), ("false", instr.goto_false)]:
                if goto_val not in EXITS and goto_val >= n:
                    msgs.append(LintMessage(
                        "error", label,
                        f"Node {j} (opcode=0x{instr.opcode:04X}): goto_{goto_name}={goto_val} "
                        f"is out of range (BHAV has {n} nodes, valid: 0-{n-1} or true/false/error)"
                    ))

            for k, op_val in enumerate(instr.operands):
                if not (0 <= op_val <= 255):
                    msgs.append(LintMessage(
                        "error", label,
                        f"Node {j}: operand {k} = {op_val} is outside uint8 range 0-255"
                    ))

    # ── Pass 2b: BHAV calls other BHAVs via opcode 0x0019 ───────────────────────
    # Opcode 0x0019 = Run Sub-BHAV: operands[0]=inst_low, operands[1]=inst_high
    CALL_OPCODE = 0x0019

    for inst_id, bhav in decoded_bhavs.items():
        label = f"BHAV '{bhav.name}' (inst=0x{inst_id:08X})"
        for instr in bhav.instructions:
            if instr.opcode == CALL_OPCODE:
                ops = instr.operands
                called_inst = ops[0] | (ops[1] << 8)
                if called_inst != 0 and called_inst not in all_bhav_insts:
                    msgs.append(LintMessage(
                        "info", label,
                        f"Node {instr.index} calls sub-BHAV 0x{called_inst:04X} "
                        f"not found in this package (may be base game BHAV — OK if intentional)"
                    ))

    # ── Pass 3: OBJf → BHAV reference checks ────────────────────────────────
    all_bhav_insts = set(decoded_bhavs.keys())

    for objf, src in zip(decoded_objfs, objf_sources):
        label = f"OBJf '{objf.name}' (inst=0x{objf.instance_id:08X})"
        for slot_i, slot in enumerate(objf.entries):
            if slot.action_bhav != 0 and slot.action_bhav not in all_bhav_insts:
                msgs.append(LintMessage(
                    "warning", label,
                    f"Slot {slot_i} action BHAV 0x{slot.action_bhav:08X} not found in this package "
                    f"(may be in a base game or EP file — OK if intentional)"
                ))
            if slot.guard_bhav != 0 and slot.guard_bhav not in all_bhav_insts:
                msgs.append(LintMessage(
                    "warning", label,
                    f"Slot {slot_i} guard BHAV 0x{slot.guard_bhav:08X} not found in this package"
                ))

    # ── Pass 4: TPRP → BHAV cross-check ─────────────────────────────────────
    for tprp, src in decoded_tprps:
        if tprp.instance_id not in all_bhav_insts:
            msgs.append(LintMessage(
                "info", f"TPRP '{tprp.name}' (inst=0x{tprp.instance_id:08X})",
                "No BHAV with matching instance ID found in this package — "
                "SimPE links TPRP to BHAV by instance, ensure they match"
            ))

    return msgs


def print_lint_report(msgs: list[LintMessage], verbose: bool = True) -> tuple[int, int]:
    """Print lint messages. Returns (error_count, warning_count)."""
    errors   = [m for m in msgs if m.level == "error"]
    warnings = [m for m in msgs if m.level == "warning"]
    infos    = [m for m in msgs if m.level == "info"]

    if not msgs:
        if verbose:
            print("  ✓ No lint issues found")
        return 0, 0

    if verbose:
        for m in errors + warnings + (infos if verbose else []):
            print(str(m))
        print(f"\n  {len(errors)} error(s), {len(warnings)} warning(s), {len(infos)} info(s)")

    return len(errors), len(warnings)
