"""
opcodes.py
Sims 2 BHAV primitive opcode reference table.
Used by the decompiler to annotate XML output with human-readable names
and by the linter to validate operand counts.

Sources: SimPE source, various community BHAV references (MTS, simbology.net, etc.)

Each entry: opcode_int -> {
    "name":     str,            human-readable primitive name
    "operands": [str, ...],     description of each operand byte (up to 8)
    "notes":    str (optional)  extra context
}
"""

OPCODES: dict[int, dict] = {
    # ── Core control flow ────────────────────────────────────────────────────
    0x0001: {
        "name": "Sleep",
        "operands": ["ticks (0=1 frame)", "", "", "", "", "", "", ""],
        "notes": "Pauses tree for N game ticks. 0 = yield for one frame.",
    },
    0x0002: {
        "name": "Notify / Log Message",
        "operands": ["string index (STR# 256)", "", "", "", "", "", "", ""],
        "notes": "Fires a TNS notification using indexed string. Also used for debug logging.",
    },
    0x0003: {
        "name": "Expression",
        "operands": [
            "LHS type (0=temp,1=local,2=param,3=global,4=attr,6=data)",
            "LHS index",
            "operator (0=set,1=add,2=sub,3=mul,4=div,5=and,6=or,7=xor,8=mod)",
            "RHS type (same as LHS type codes, 0x80 = literal)",
            "RHS low byte",
            "RHS high byte",
            "", "",
        ],
        "notes": "General-purpose expression/assignment primitive.",
    },
    0x0004: {
        "name": "Find Best Action",
        "operands": ["", "", "", "", "", "", "", ""],
        "notes": "Searches interaction queue for next best action.",
    },
    0x0005: {
        "name": "Get/Set Object",
        "operands": ["operation", "object slot", "stack object index", "", "", "", "", ""],
    },
    0x0006: {
        "name": "Add / Remove Named Object",
        "operands": ["operation (0=add,1=remove)", "name STR# index", "", "", "", "", "", ""],
    },
    0x0007: {
        "name": "Relationship (Get/Set Daily)",
        "operands": ["operation (0=get,1=set,2=add,3=sub)", "target index", "temp destination", "", "", "", "", ""],
    },
    0x0008: {
        "name": "Push Interaction",
        "operands": ["interaction index", "priority", "stack obj index", "", "", "", "", ""],
    },
    0x0009: {
        "name": "Find Best Interaction",
        "operands": ["", "", "", "", "", "", "", ""],
    },
    0x000A: {
        "name": "Animate Sim",
        "operands": ["animation ID", "target (0=self,1=target)", "priority", "overlay (0=no,1=yes)", "", "", "", ""],
    },
    0x000B: {
        "name": "Animate Object",
        "operands": ["animation ID", "target index", "", "", "", "", "", ""],
    },
    0x000C: {
        "name": "Go to Routing Slot",
        "operands": ["slot index", "facing (0=front,1=back,2=left,3=right)", "", "", "", "", "", ""],
    },
    0x000D: {
        "name": "Snap to Slot",
        "operands": ["slot index", "target index", "", "", "", "", "", ""],
    },
    0x000E: {
        "name": "Change Relationship",
        "operands": [
            "delta (signed int8)",
            "relationship type (0=daily,1=lifetime,2=short-term)",
            "direction (0=self→target,1=target→self,2=both)",
            "", "", "", "", "",
        ],
    },
    0x000F: {
        "name": "Change Motive",
        "operands": ["motive index", "delta (signed int8)", "target (0=self,1=target)", "", "", "", "", ""],
    },
    0x0010: {
        "name": "Go To Relative Position",
        "operands": ["x offset", "y offset", "z offset", "", "", "", "", ""],
    },
    0x0011: {
        "name": "Change Suit / Outfit",
        "operands": ["suit type", "outfit index", "target (0=self,1=target)", "", "", "", "", ""],
    },
    0x0012: {
        "name": "Shine",
        "operands": ["on/off (0=off,1=on)", "", "", "", "", "", "", ""],
    },
    0x0013: {
        "name": "Set Motive Change",
        "operands": [
            "motive index",
            "on/off",
            "delta per hour (signed int8)",
            "min value (signed int8)",
            "max value (signed int8)",
            "", "", "",
        ],
    },
    0x0014: {
        "name": "Play Sound",
        "operands": ["sound index", "looping (0=no,1=yes)", "target", "", "", "", "", ""],
    },
    0x0015: {
        "name": "Old Object Push Interaction",
        "operands": ["interaction index", "stack obj", "", "", "", "", "", ""],
    },
    0x0016: {
        "name": "Idle",
        "operands": ["", "", "", "", "", "", "", ""],
        "notes": "Yield to allow other things to run without sleeping.",
    },
    0x0017: {
        "name": "Set Dynamic String",
        "operands": ["str index", "source type", "source index", "", "", "", "", ""],
    },
    0x0018: {
        "name": "Test (Relationship)",
        "operands": [
            "relationship type (0=daily,1=lifetime,2=short-term)",
            "operator (0=less,1=less-eq,2=eq,3=greater-eq,4=greater,5=not-eq)",
            "compare value low",
            "compare value high",
            "direction (0=self→target,1=target→self)",
            "", "", "",
        ],
    },
    0x0019: {
        "name": "Call BHAV (Run Sub-tree)",
        "operands": ["BHAV instance low", "BHAV instance high", "arg 0", "arg 1", "arg 2", "arg 3", "", ""],
        "notes": "Calls another BHAV synchronously. Returns that BHAV's result.",
    },
    0x001A: {
        "name": "Notify If Object Has Motion",
        "operands": ["", "", "", "", "", "", "", ""],
    },
    0x001B: {
        "name": "Get / Set Attribute",
        "operands": ["operation", "attribute index", "temp index", "", "", "", "", ""],
    },
    0x001C: {
        "name": "Dialogue (Show)",
        "operands": ["dialog type", "string index", "button mask", "", "", "", "", ""],
    },
    0x001D: {
        "name": "Add / Remove Interaction",
        "operands": ["operation (0=add,1=remove,2=add-autonomous)", "slot index", "", "", "", "", "", ""],
    },
    0x001E: {
        "name": "Smoke Test",
        "operands": ["test type", "", "", "", "", "", "", ""],
        "notes": "Used in TS2 guard BHAVs to do quick validity checks.",
    },
    0x001F: {
        "name": "Break Point (Debug)",
        "operands": ["", "", "", "", "", "", "", ""],
        "notes": "SimPE debugger breakpoint. No effect in game.",
    },
    0x0020: {
        "name": "Find Best Object For Function",
        "operands": ["function index", "radius temp", "", "", "", "", "", ""],
    },
    0x0021: {
        "name": "Tree (Call sub-BHAV by instance)",
        "operands": ["instance low", "instance high", "", "", "", "", "", ""],
    },
    0x0022: {
        "name": "Show / Hide Headline",
        "operands": ["headline type", "on/off", "target (0=self,1=target)", "", "", "", "", ""],
    },
    0x0025: {
        "name": "Change Relationship (Extended)",
        "operands": [
            "delta (signed int8)",
            "type (0=daily,1=lifetime,2=short-term)",
            "direction (0=self→target,1=target→self,2=both)",
            "", "", "", "", "",
        ],
    },
    0x0027: {
        "name": "Get / Test Relationship",
        "operands": [
            "operation (0=get into temp,1=test)",
            "type (0=daily,1=lifetime,2=short-term)",
            "temp destination",
            "direction (0=self→target,1=target→self)",
            "", "", "", "",
        ],
    },
    0x002B: {
        "name": "Social Interaction",
        "operands": ["interaction index", "initiator (0=self,1=target)", "", "", "", "", "", ""],
    },
    0x002E: {
        "name": "Reach For (routing)",
        "operands": ["slot index", "direction", "", "", "", "", "", ""],
    },
    0x0041: {
        "name": "Get Distance To Object",
        "operands": ["target index", "temp destination", "", "", "", "", "", ""],
    },
    0x0083: {
        "name": "Play Sound (Extended)",
        "operands": ["sound group low", "sound group high", "instance low", "instance high", "", "", "", ""],
    },
    0x009B: {
        "name": "Test Sim Flags",
        "operands": ["flag index", "expected value (0=off,1=on)", "target (0=self,1=target)", "", "", "", "", ""],
    },
    0x00BC: {
        "name": "Set Sim Flag",
        "operands": ["flag index", "value (0=off,1=on)", "target (0=self,1=target)", "", "", "", "", ""],
    },
    0x010B: {
        "name": "Idle Animation",
        "operands": ["animation ID", "target", "blend time", "", "", "", "", ""],
    },
    0x014E: {
        "name": "Test / Set Sim Flag (Extended)",
        "operands": ["flag index", "operation", "value", "", "", "", "", ""],
    },
    0x01E6: {
        "name": "Notify (TNS Extended)",
        "operands": ["string index", "icon type", "color", "", "", "", "", ""],
    },
    0x0229: {
        "name": "Smoke Test (Extended)",
        "operands": ["type", "target", "", "", "", "", "", ""],
    },
    0x0257: {
        "name": "Test Sim Relationship Flags",
        "operands": ["flag index", "expected", "target", "", "", "", "", ""],
    },
    # ── Sentinel ─────────────────────────────────────────────────────────────
    0xFFFF: {
        "name": "Error / Fence",
        "operands": ["", "", "", "", "", "", "", ""],
        "notes": "Marks end of BHAV or deliberate error node.",
    },
}


def lookup(opcode: int) -> dict:
    """Return opcode info dict, or a generic placeholder if unknown."""
    return OPCODES.get(opcode, {
        "name": f"Unknown (0x{opcode:04X})",
        "operands": ["op0", "op1", "op2", "op3", "op4", "op5", "op6", "op7"],
    })


def name(opcode: int) -> str:
    return lookup(opcode)["name"]


def operand_labels(opcode: int) -> list[str]:
    return lookup(opcode).get("operands", [""] * 8)
