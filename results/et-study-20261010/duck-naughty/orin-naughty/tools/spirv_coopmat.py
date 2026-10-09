#!/usr/bin/env python3
"""spirv_coopmat.py <out.csv> <name=path.spv>...: disassemble each SPIR-V module (spirv-dis) and list every
OpTypeCooperativeMatrixKHR (component type, rows, columns, use, scope; spec constants are resolved to their default
value and marked) and every OpCooperativeMatrixMulAddKHR with the types of its A, B, C operands and of its result.
Also counts loads/stores of cooperative matrices and the local size. Read-only on the inputs."""
import csv, re, subprocess, sys
USE = {0: "A", 1: "B", 2: "Acc"}
def analyse(name, path):
    txt = subprocess.run(["spirv-dis", "--raw-id", path], capture_output=True, text=True, check=True).stdout
    scal, const, cm, typ_of, rows = {}, {}, {}, {}, []
    lines = txt.splitlines()
    for l in lines:
        m = re.match(r"\s*(%\d+) = (Op\w+)\s*(.*)", l)
        if not m:
            continue
        rid, op, rest = m.groups(); a = rest.split()
        if op == "OpTypeFloat": scal[rid] = f"float{a[0]}"
        elif op == "OpTypeInt": scal[rid] = f"{'s' if a[1] == '1' else 'u'}int{a[0]}"
        elif op in ("OpConstant", "OpSpecConstant"): const[rid] = (a[1], op == "OpSpecConstant")
        elif op == "OpTypeCooperativeMatrixKHR": cm[rid] = a  # comp scope rows cols use
        elif op == "OpTypePointer": pass
        elif len(a) >= 1 and a[0].startswith("%"): typ_of[rid] = a[0]
    def cv(i):
        v, spec = const.get(i, ("?", False)); return f"{v}{'(spec default)' if spec else ''}"
    def cmdesc(t):
        c = cm[t]; return f"{scal.get(c[0], c[0])} {cv(c[2])}x{cv(c[3])} use={USE.get(int(const.get(c[4], ('9',))[0]), '?')} scope={cv(c[1])}"
    for t in cm: rows.append([name, "type", t, cmdesc(t), "", "", ""])
    nmul = 0
    for l in lines:
        m = re.match(r"\s*(%\d+) = OpCooperativeMatrixMulAddKHR (%\d+) (%\d+) (%\d+) (%\d+)(.*)", l)
        if m:
            nmul += 1; rid, rt, A, B, C, extra = m.groups()
            rows.append([name, "muladd", rid, "result: " + cmdesc(rt), "A: " + cmdesc(typ_of[A]), "B: " + cmdesc(typ_of[B]), "C: " + cmdesc(typ_of[C]) + (" operands:" + extra.strip() if extra.strip() else "")])
    cnt = lambda op: sum(1 for l in lines if re.search(rf"\b{op}\b", l))
    ls = next((l.strip() for l in lines if "OpExecutionMode" in l and "LocalSize" in l), "")
    rows.append([name, "counts", "", f"static MulAdd={nmul}", f"CooperativeMatrixLoad={cnt('OpCooperativeMatrixLoadKHR')}", f"CooperativeMatrixStore={cnt('OpCooperativeMatrixStoreKHR')}", f"ControlBarrier={cnt('OpControlBarrier')} {ls}"])
    return rows
w = csv.writer(open(sys.argv[1], "w", newline="")); w.writerow(["shader", "kind", "id", "c1", "c2", "c3", "c4"])
for arg in sys.argv[2:]:
    n, p = arg.split("=", 1)
    for r in analyse(n, p): w.writerow(r)
