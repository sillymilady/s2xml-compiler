"""
bhav_xml_helpers.py
Parses the high-level BHAV XML sugar elements:

  <expression lhs="temp:0"  op="="   rhs="lit:60"  true="1" false="false"/>
  <test       lhs="temp:0"  cmp=">=" rhs="lit:60"  true="2" false="false"/>
  <call       bhav="0x1001" arg0="0" arg1="0"       true="1" false="false"/>

These are translated to BHAVInstruction objects during compile.
Named constants (rhs="$MY_CONST") are resolved in a second pass.
"""

import xml.etree.ElementTree as ET
from bhav_encoder import BHAVInstruction, EXIT_TRUE, EXIT_FALSE, EXIT_ERROR
from bhav_sugar   import expression, test_expr, call_bhav, SOURCE_TYPES, COMPARE_OPS

GOTO_ALIASES = {
    "true":       EXIT_TRUE,
    "false":      EXIT_FALSE,
    "error":      EXIT_ERROR,
    "exit_true":  EXIT_TRUE,
    "exit_false": EXIT_FALSE,
}

# Sentinal used during constant resolution pass
_UNRESOLVED = object()


def _goto(s) -> int:
    if s is None:
        return EXIT_TRUE
    s = s.strip().lower()
    if s in GOTO_ALIASES:
        return GOTO_ALIASES[s]
    try:
        return int(s, 0)
    except ValueError:
        return EXIT_TRUE


def _resolve_ref(ref: str, constants: dict) -> str:
    """
    If ref starts with '$', look up the constant name and return a lit: source.
    Otherwise return ref unchanged.
    constants: dict mapping name → int value (collected from TRCN/BCON in the package).
    """
    ref = ref.strip()
    if ref.startswith("$"):
        name = ref[1:]
        if name not in constants:
            raise ValueError(
                f"Constant '${name}' not defined. "
                f"Available: {', '.join('$'+k for k in sorted(constants))}"
            )
        return f"lit:{constants[name]}"
    return ref


def parse_bhav_element(root: ET.Element, constants: dict = None) -> list:
    """
    Parse all child elements of a <bhav> root and return a list of BHAVInstruction.
    Handles <instruction>, <expression>, <test>, and <call> elements.
    constants: optional dict of name→int for $CONST substitution.
    """
    constants = constants or {}
    instructions = []

    for el in root:
        tag = el.tag.lower()
        gt  = _goto(el.get("true",  "true"))
        gf  = _goto(el.get("false", "false"))
        cmt = el.get("comment", "").strip()

        if tag == "instruction":
            # Raw instruction — handled by existing parser
            # (this function is called for the full parse, so we include it)
            from xml_parser import _int, _goto as _pg
            opcode = _int(el.get("opcode"), 0)
            nv     = _int(el.get("node_version"), 0xFE)
            ops = [0] * 8
            op_csv = el.get("operands", "")
            if op_csv:
                for i, p in enumerate(op_csv.split(",")[:8]):
                    ops[i] = _int(p.strip()) & 0xFF
            else:
                for i in range(8):
                    v = el.get(f"op{i}") or el.get(f"operand{i}")
                    if v is not None:
                        ops[i] = _int(v) & 0xFF
            instructions.append(BHAVInstruction(
                opcode=opcode, goto_true=gt, goto_false=gf,
                node_version=nv, operands=ops, comment=cmt,
            ))

        elif tag == "expression":
            lhs = _resolve_ref(el.get("lhs", "temp:0"), constants)
            op  = el.get("op", el.get("operator", "="))
            rhs = _resolve_ref(el.get("rhs", "lit:0"),  constants)
            instr = expression(lhs, op, rhs, goto_true=gt, goto_false=gf)
            instr.comment = cmt or instr.comment
            instructions.append(instr)

        elif tag == "test":
            lhs = _resolve_ref(el.get("lhs", "temp:0"), constants)
            cmp = el.get("cmp", el.get("compare", el.get("op", ">=")))
            rhs = _resolve_ref(el.get("rhs", "lit:0"),  constants)
            instr = test_expr(lhs, cmp, rhs, goto_true=gt, goto_false=gf)
            instr.comment = cmt or instr.comment
            instructions.append(instr)

        elif tag == "call":
            from xml_parser import _int
            inst = _int(el.get("bhav", el.get("instance", "0")))
            args = [_int(el.get(f"arg{i}"), 0) for i in range(4)]
            instr = call_bhav(inst, args, goto_true=gt, goto_false=gf)
            instr.comment = cmt or instr.comment
            instructions.append(instr)

        elif tag == "sleep":
            from xml_parser import _int
            from bhav_sugar import sleep
            ticks = _int(el.get("ticks", "0"), 0)
            instr = sleep(ticks, goto_true=gt, comment=cmt)
            instructions.append(instr)

        elif tag == "animate":
            from xml_parser import _int
            from bhav_sugar import animate
            instr = animate(
                _int(el.get("id", "0")),
                _int(el.get("target", "0")),
                _int(el.get("priority", "5")),
                goto_true=gt, goto_false=gf, comment=cmt,
            )
            instructions.append(instr)

        elif tag == "rel_change":
            from xml_parser import _int
            from bhav_sugar import change_relationship
            instr = change_relationship(
                _int(el.get("delta", "0")),
                _int(el.get("type",  "0")),
                _int(el.get("direction", "2")),
                goto_true=gt, goto_false=gf, comment=cmt,
            )
            instructions.append(instr)

        elif tag == "get_rel":
            from xml_parser import _int
            from bhav_sugar import get_relationship
            instr = get_relationship(
                _int(el.get("dest", "0")),
                _int(el.get("type", "0")),
                _int(el.get("direction", "0")),
                goto_true=gt, goto_false=gf, comment=cmt,
            )
            instructions.append(instr)

        # Ignore XML comments and unknown tags silently
        # (ET strips <!-- --> on parse anyway)

    return instructions
