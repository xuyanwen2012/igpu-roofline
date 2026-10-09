#!/usr/bin/env python3
"""spirv_types.py <file.spv>...: per SPIR-V module, the OpTypeCooperativeMatrixKHR types (component type,
rows, columns, use: 0 = A, 1 = B, 2 = accumulator) and, for every OpCooperativeMatrixMulAddKHR, the types of
its A, B and C operands and of its result. Uses spirv-dis; prints CSV:
module,kind,id_or_count,component,rows,cols,use / module,muladd,count,A,B,C,result"""
import collections, re, subprocess, sys
USE = {0: "A", 1: "B", 2: "Acc"}
for path in sys.argv[1:]:
    txt = subprocess.run(["spirv-dis", "--raw-id", path], capture_output=True, text=True, check=True).stdout
    name = path.rsplit("/", 1)[-1].removesuffix(".spv")
    scal, const, cm, rtype = {}, {}, {}, {}
    muls = collections.Counter()
    lines = txt.splitlines()
    for l in lines:
        m = re.match(r"\s*(%\d+) = OpTypeFloat (\d+)", l)
        if m: scal[m[1]] = "fp" + m[2]
        m = re.match(r"\s*(%\d+) = OpTypeInt (\d+) (\d)", l)
        if m: scal[m[1]] = ("s" if m[3] == "1" else "u") + "int" + m[2]
        m = re.match(r"\s*(%\d+) = OpConstant (%\d+) (\S+)", l)
        if m: const[m[1]] = m[3]
        m = re.match(r"\s*(%\d+) = OpTypeCooperativeMatrixKHR (%\d+) (%\d+) (%\d+) (%\d+) (%\d+)", l)
        if m: cm[m[1]] = (scal[m[2]], const[m[4]], const[m[5]], USE[int(const[m[6]])])
        m = re.match(r"\s*(%\d+) = Op\w+ (%\d+)", l)
        if m: rtype[m[1]] = m[2]
    def t(i):
        c = cm[rtype[i]] if i in rtype and rtype[i] in cm else None
        return f"{c[0]} {c[1]}x{c[2]} {c[3]}" if c else "?"
    for l in lines:
        m = re.match(r"\s*(%\d+) = OpCooperativeMatrixMulAddKHR (%\d+) (%\d+) (%\d+) (%\d+)(.*)", l)
        if m:
            c = cm[m[2]]
            muls[(t(m[3]), t(m[4]), t(m[5]), f"{c[0]} {c[1]}x{c[2]} {c[3]}", m[6].strip())] += 1
    for i, c in cm.items():
        print(f"{name},type,{i},{c[0]},{c[1]},{c[2]},{c[3]}")
    for (a, b, c, r, ops), n in muls.items():
        print(f"{name},muladd,{n},{a},{b},{c},{r},{ops or '-'}")
    ver = re.search(r"; Version: (\S+)", txt)
    print(f"{name},version,{ver[1] if ver else '?'}")
