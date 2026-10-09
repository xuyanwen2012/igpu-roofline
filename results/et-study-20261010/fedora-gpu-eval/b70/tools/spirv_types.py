#!/usr/bin/env python3
"""spirv_types.py <out.csv> <kernel.spvasm...>: cooperative-matrix types of a kernel, read from its SPIR-V.

Operand order relied on (vulkan-docs `spirv_opcode`, core grammar):
  OpTypeCooperativeMatrixKHR   IdResult, Component Type, Scope, Rows, Columns, Use
  OpCooperativeMatrixMulAddKHR IdResultType, IdResult, A, B, C, [Cooperative Matrix Operands]
Use 0 = MatrixA, 1 = MatrixB, 2 = MatrixAccumulator. One row per kernel: the component type and shape of every
cooperative-matrix type, and for the multiply-adds the set of (A type, B type, C type, result type) and their
count. in_type = component of A and B, acc_type = component of the result, mma_shape = M x N x K
(rows of A x columns of B x columns of A)."""
import collections, csv, os, re, sys

NAMES = {"half": "fp16", "float": "fp32", "char": "int8", "uchar": "uint8", "int": "int32", "uint": "uint32"}
out = csv.writer(open(sys.argv[1], "w", newline=""))
out.writerow(["kernel", "coopmat_types", "muladd_count", "muladd_signatures", "in_type", "acc_type", "mma_shape"])
for path in sys.argv[2:]:
    text = open(path).read()
    const = {m[1]: int(m[2]) for m in re.finditer(r"%(\w+) = OpConstant %u?int (\d+)", text)}
    types = {}
    for m in re.finditer(r"%(\w+) = OpTypeCooperativeMatrixKHR %(\w+) %(\w+) %(\w+) %(\w+) %(\w+)", text):
        types[m[1]] = (NAMES.get(m[2], m[2]), const[m[4]], const[m[5]], const[m[6]])
    idtype = {m[1]: m[2] for m in re.finditer(r"%(\w+) = Op\w+ %(\w+)", text)}
    sig = collections.Counter()
    for m in re.finditer(r"%(\w+) = OpCooperativeMatrixMulAddKHR %(\w+) %(\w+) %(\w+) %(\w+)", text):
        sig[(idtype[m[3]], idtype[m[4]], idtype[m[5]], m[2])] += 1
    fmt = lambda t: "%s %dx%d use%d" % types[t]
    ins, accs, shapes = set(), set(), set()
    for a, b, c, r in sig:
        ins |= {types[a][0], types[b][0]}; accs |= {types[r][0], types[c][0]}
        shapes.add("%dx%dx%d" % (types[a][1], types[b][2], types[a][2]))
    out.writerow([os.path.basename(path).replace(".spvasm", ""), "; ".join(fmt(t) for t in sorted(types)), sum(sig.values()),
                  "; ".join("A[%s] B[%s] C[%s] -> %s (x%d)" % (fmt(a), fmt(b), fmt(c), fmt(r), n) for (a, b, c, r), n in sig.items()),
                  "+".join(sorted(ins)), "+".join(sorted(accs)), "+".join(sorted(shapes))])
