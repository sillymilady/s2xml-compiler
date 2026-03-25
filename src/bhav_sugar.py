"""
bhav_sugar.py
High-level BHAV authoring helpers that compile to raw BHAVInstruction objects.

Eliminates the need to manually calculate Expression operand bytes,
sub-BHAV call instance splits, and other tedious encoding work.

EXPRESSION OPERAND ENCODING (opcode 0x0003)
───────────────────────────────────────────
Byte layout:
  op0  LHS type  (0=temp, 1=local, 2=param, 3=global, 4=attribute, 6=data)
  op1  LHS index
  op2  operator  (0=set, 1=add, 2=sub, 3=mul, 4=div, 5=and, 6=or, 7=xor, 8=mod)
  op3  RHS type  (same codes + 0x80=literal)
  op4  RHS low byte   (if literal: signed low byte of value)
  op5  RHS high byte  (if literal: signed high byte of value)
  op6  0
  op7  0

SOURCE REFERENCE ENCODING (LHS/RHS)
────────────────────────────────────
String form "type:index_or_value":
  temp:N      temp register N       → type=0, index=N
  local:N     local variable N      → type=1, index=N
  param:N     parameter N           → type=2, index=N
  global:N    global variable N     → type=3, index=N
  attr:N      object attribute N    → type=4, index=N
  data:N      object data N         → type=6, index=N
  lit:V       literal value V       → type=0x80, value packed as int16 LE

OPERATOR NAMES
──────────────
  =    set
  +=   add
  -=   sub  (also: subtract)
  *=   mul  (also: multiply)
  /=   div  (also: divide)
  &=   and
  |=   or
  ^=   xor
  %=   mod  (also: modulo)
"""

from bhav_encoder import BHAVInstruction, EXIT_TRUE, EXIT_FALSE

# ── Reference tables ──────────────────────────────────────────────────────────

SOURCE_TYPES = {
    "temp":   0, "t":    0,
    "local":  1, "l":    1,
    "param":  2, "p":    2,
    "global": 3, "g":    3,
    "attr":   4, "a":    4,
    "data":   6, "d":    6,
    "lit":    0x80, "literal": 0x80, "const": 0x80,
}

OPERATORS = {
    "=":   0, "set":      0,
    "+=":  1, "add":      1,
    "-=":  2, "sub":      2, "subtract":  2,
    "*=":  3, "mul":      3, "multiply":  3,
    "/=":  4, "div":      4, "divide":    4,
    "&=":  5, "and":      5,
    "|=":  6, "or":       6,
    "^=":  7, "xor":      7,
    "%=":  8, "mod":      8, "modulo":    8,
}

COMPARE_OPS = {
    "<":  0, "lt":  0, "less":         0,
    "<=": 1, "le":  1, "less-eq":      1, "lessequal":   1,
    "==": 2, "eq":  2, "equal":        2,
    ">=": 3, "ge":  3, "greater-eq":   3, "greaterequal":3,
    ">":  4, "gt":  4, "greater":      4,
    "!=": 5, "ne":  5, "not-eq":       5, "notequal":    5,
}


def _parse_source(s: str) -> tuple[int, int]:
    """
    Parse "type:value" into (type_byte, value_int).
    e.g. "temp:0" → (0, 0),  "lit:60" → (0x80, 60),  "local:2" → (1, 2)
    Raises ValueError on bad format.
    """
    s = s.strip()
    if ":" not in s:
        raise ValueError(
            f"Source '{s}' must be 'type:value' e.g. 'temp:0', 'lit:60', 'param:1'"
        )
    prefix, _, val_str = s.partition(":")
    prefix = prefix.lower().strip()
    if prefix not in SOURCE_TYPES:
        raise ValueError(
            f"Unknown source type '{prefix}'. Valid: {', '.join(sorted(set(SOURCE_TYPES)))}"
        )
    type_byte = SOURCE_TYPES[prefix]
    try:
        value = int(val_str.strip(), 0)
    except ValueError:
        raise ValueError(f"Source value '{val_str}' is not a valid integer")
    return type_byte, value


def _parse_operator(s: str) -> int:
    key = s.strip().lower()
    if key not in OPERATORS:
        raise ValueError(
            f"Unknown operator '{s}'. Valid: {', '.join(sorted(set(OPERATORS)))}"
        )
    return OPERATORS[key]


def _parse_compare_op(s: str) -> int:
    key = s.strip().lower()
    if key not in COMPARE_OPS:
        raise ValueError(
            f"Unknown compare op '{s}'. Valid: {', '.join(sorted(set(COMPARE_OPS)))}"
        )
    return COMPARE_OPS[key]


# ── Sugar builders ────────────────────────────────────────────────────────────

def expression(lhs: str, op: str, rhs: str,
                goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
                comment: str = "") -> BHAVInstruction:
    """
    Build an Expression instruction (opcode 0x0003).

    Args:
        lhs:  source string e.g. "temp:0", "local:2", "attr:5"
        op:   operator string e.g. "=", "+=", "set", "add"
        rhs:  source string e.g. "lit:60", "temp:1", "param:0"

    Examples:
        expression("temp:0", "=",  "lit:60")     # temp[0] = 60
        expression("temp:0", "+=", "param:0")    # temp[0] += param[0]
        expression("attr:2", "=",  "lit:0")      # attribute[2] = 0
        expression("local:0","set","global:3")   # local[0] = global[3]
    """
    lhs_type, lhs_idx = _parse_source(lhs)
    op_byte            = _parse_operator(op)
    rhs_type, rhs_val  = _parse_source(rhs)

    ops = [lhs_type & 0xFF, lhs_idx & 0xFF, op_byte & 0xFF, rhs_type & 0xFF,
           0, 0, 0, 0]

    if rhs_type == 0x80:  # literal — pack as signed int16 LE
        packed = rhs_val & 0xFFFF  # handles negative numbers
        ops[4] = packed & 0xFF
        ops[5] = (packed >> 8) & 0xFF
    else:
        ops[4] = rhs_val & 0xFF

    return BHAVInstruction(
        opcode=0x0003,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=ops,
        comment=comment or f"{lhs} {op} {rhs}",
    )


def test_expr(lhs: str, compare: str, rhs: str,
              goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
              comment: str = "") -> BHAVInstruction:
    """
    Build a Test / Compare Expression instruction (opcode 0x0003 with test flag).

    This is the "if" form of Expression — it doesn't assign, it compares.
    In TS2 BHAVs, comparison is done by setting LHS type to the value to test
    and using a special operator encoding. The standard approach is:
      op2 = compare opcode (from COMPARE_OPS) | 0x80 (test flag)

    Args:
        lhs:     left-hand operand  e.g. "temp:0"
        compare: comparison string  e.g. ">=", "==", "lt"
        rhs:     right-hand operand e.g. "lit:60"

    Examples:
        test_expr("temp:0", ">=", "lit:60")   # if temp[0] >= 60 → true
        test_expr("attr:3", "==", "lit:0")    # if attribute[3] == 0 → true
    """
    lhs_type, lhs_idx = _parse_source(lhs)
    cmp_op             = _parse_compare_op(compare)
    rhs_type, rhs_val  = _parse_source(rhs)

    ops = [lhs_type & 0xFF, lhs_idx & 0xFF,
           (cmp_op | 0x80) & 0xFF,   # 0x80 flag = test mode
           rhs_type & 0xFF, 0, 0, 0, 0]

    if rhs_type == 0x80:
        packed = rhs_val & 0xFFFF
        ops[4] = packed & 0xFF
        ops[5] = (packed >> 8) & 0xFF
    else:
        ops[4] = rhs_val & 0xFF

    return BHAVInstruction(
        opcode=0x0003,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=ops,
        comment=comment or f"if {lhs} {compare} {rhs}",
    )


def call_bhav(instance: int, args: list[int] = None,
              goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
              comment: str = "") -> BHAVInstruction:
    """
    Build a Call BHAV instruction (opcode 0x0019).

    Args:
        instance: BHAV instance ID (e.g. 0x1001)
        args:     up to 4 argument values (passed as params to sub-BHAV)

    Example:
        call_bhav(0x1001)                    # call BHAV 0x1001
        call_bhav(0x1001, args=[5, 0])       # call with param[0]=5, param[1]=0
    """
    args = (list(args or []) + [0, 0, 0, 0])[:4]
    inst_low  = instance & 0xFF
    inst_high = (instance >> 8) & 0xFF
    ops = [inst_low, inst_high] + [a & 0xFF for a in args] + [0, 0]
    return BHAVInstruction(
        opcode=0x0019,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=ops,
        comment=comment or f"call BHAV 0x{instance:04X}",
    )


def sleep(ticks: int = 0, goto_true=EXIT_TRUE, comment: str = "") -> BHAVInstruction:
    """Sleep for N ticks. 0 = yield one frame."""
    return BHAVInstruction(opcode=0x0001, goto_true=goto_true,
                           operands=[ticks & 0xFF] + [0]*7,
                           comment=comment or f"sleep {ticks} ticks")


def ret_true() -> BHAVInstruction:
    """Return True from BHAV."""
    return BHAVInstruction(opcode=0x0001, goto_true=EXIT_TRUE,
                           goto_false=EXIT_TRUE, comment="return true")


def ret_false() -> BHAVInstruction:
    """Return False from BHAV."""
    return BHAVInstruction(opcode=0x0001, goto_true=EXIT_FALSE,
                           goto_false=EXIT_FALSE, comment="return false")


def change_relationship(delta: int, rel_type: int = 0, direction: int = 2,
                        goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
                        comment: str = "") -> BHAVInstruction:
    """
    Change relationship (opcode 0x0025 extended).
    rel_type:  0=daily, 1=lifetime, 2=short-term
    direction: 0=self→target, 1=target→self, 2=both
    """
    d = delta & 0xFF  # signed byte
    return BHAVInstruction(
        opcode=0x0025,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=[d, rel_type & 0xFF, direction & 0xFF, 0, 0, 0, 0, 0],
        comment=comment or f"relationship delta={delta} type={rel_type} dir={direction}",
    )


def animate(anim_id: int, target: int = 0, priority: int = 5,
            goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
            comment: str = "") -> BHAVInstruction:
    """
    Animate a sim (opcode 0x000A).
    target: 0=self, 1=interaction target
    """
    return BHAVInstruction(
        opcode=0x000A,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=[anim_id & 0xFF, target & 0xFF, priority & 0xFF, 0, 0, 0, 0, 0],
        comment=comment or f"animate id={anim_id} target={target}",
    )


def get_relationship(dest_temp: int = 0, rel_type: int = 0, direction: int = 0,
                     goto_true=EXIT_TRUE, goto_false=EXIT_FALSE,
                     comment: str = "") -> BHAVInstruction:
    """
    Get relationship value into a temp register (opcode 0x0027, op=get).
    dest_temp: temp register index to store result in
    """
    return BHAVInstruction(
        opcode=0x0027,
        goto_true=goto_true,
        goto_false=goto_false,
        operands=[0, rel_type & 0xFF, dest_temp & 0xFF, direction & 0xFF, 0, 0, 0, 0],
        comment=comment or f"get rel type={rel_type} → temp:{dest_temp}",
    )
