#!/usr/bin/env python3
"""spirv_mma.py <file.spvasm>... : cooperative-matrix types and every OpCooperativeMatrixMulAddKHR of a
disassembled SPIR-V module (spirv-dis output), with the types of its result and of operands A, B, C.
Prints one CSV block per file and a summary line; also counts the other instructions that produce or consume
cooperative matrices (loads, stores, conversions, adds) by result/operand type."""
import collections, re, sys

USE = {"0": "A", "1": "B", "2": "Acc"}
for path in sys.argv[1:]:
    types, const, rtype, lines = {}, {}, {}, []
    for ln in open(path):
        m = re.match(r"\s*(%\S+) = (Op\S+)\s*(.*)", ln)
        if not m:
            lines.append((None, ln.split()[0] if ln.split() else "", ln.split()[1:]))
            continue
        rid, op, rest = m.group(1), m.group(2), m.group(3).split()
        lines.append((rid, op, rest))
        if op == "OpConstant":
            const[rid] = rest[1]
        if op == "OpTypeCooperativeMatrixKHR":
            comp, scope, rows, cols, use = rest
            types[rid] = f"{comp[1:]} {const.get(rows, rows)}x{const.get(cols, cols)} {USE.get(const.get(use, use), use)}"
        elif not op.startswith("OpType") and rest:
            rtype[rid] = rest[0]
    name = path.split("/")[-1].replace(".spvasm", "")
    print(f"# {name}")
    for k, v in types.items():
        print(f"type,{k},{v}")
    mma = collections.Counter(); other = collections.Counter()
    for rid, op, rest in lines:
        if op == "OpCooperativeMatrixMulAddKHR":
            res, a, b, c = rest[0], rest[1], rest[2], rest[3]
            mma[(types[res], types[rtype[a]], types[rtype[b]], types[rtype[c]])] += 1
        elif rid and rest and rest[0] in types:
            src = [types[rtype[x]] for x in rest[1:] if x in rtype and rtype[x] in types]
            other[(op, types[rest[0]], " | ".join(src))] += 1
        elif op == "OpCooperativeMatrixStoreKHR":
            other[(op, "", types.get(rtype.get(rest[1]), "?"))] += 1
    for (res, a, b, c), n in mma.items():
        print(f"muladd,count={n},result=[{res}],A=[{a}],B=[{b}],C=[{c}]")
    for (op, res, src), n in sorted(other.items()):
        print(f"other,count={n},{op},result=[{res}],from=[{src}]")
    print(f"summary,{name},muladd_total={sum(mma.values())}")
