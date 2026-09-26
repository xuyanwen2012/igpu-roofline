"""Add SPIR-V `Volatile` to Workgroup loads/stores (GLSL cannot express this).

Without it a compiler may keep workgroup-memory values in registers or forward a
store to a later load, and the shared-memory benchmark would not touch shared
memory at all. Only memory-access operands change; pointer storage classes are
resolved from SPIR-V types, so buffer and function-local accesses stay untouched.
The caller re-assembles and re-validates the module.
"""

import re


def annotate(text: str) -> tuple[str, int]:
    workgroup_types = set(re.findall(r"(%\w+) = OpTypePointer Workgroup ", text))
    pointers = set()
    for line in text.splitlines():
        m = re.search(r"(%\w+) = \w+ (%\w+)", line)
        if m and m[2] in workgroup_types:
            pointers.add(m[1])

    out, count = [], 0
    for line in text.splitlines():
        m = re.search(r"= OpLoad %\w+ (%\w+)(.*)$", line) or re.search(
            r"OpStore (%\w+) %\w+(.*)$", line
        )
        if m and m[1] in pointers:
            assert not m[2].strip(), (
                "Unexpected memory-operand mask; extend the parser explicitly"
            )
            line += " Volatile"
            count += 1
        out.append(line)
    assert count > 0, "no workgroup accesses found"
    return "\n".join(out) + "\n", count
