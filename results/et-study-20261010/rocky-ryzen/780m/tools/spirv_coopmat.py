#!/usr/bin/env python3
"""List cooperative-matrix types and multiply-add operand types of SPIR-V disassemblies (spirv-dis output).

Usage: spirv_coopmat.py <file.spvasm>...   prints CSV to stdout.
Per file: every OpTypeCooperativeMatrixKHR (component, rows, cols, use), and for the
OpCooperativeMatrixMulAddKHR instructions the (A, B, C) -> result type signature with its count, the
number of distinct A and B operand ids, where those operands are loaded from (storage class of the
pointer of their OpCooperativeMatrixLoadKHR), and the static matrix operations per loaded operand byte:
  ops_per_loaded_byte = n_muladd * 2*rows*cols*K / (n_distinct_loaded_operands * rows_x_cols * bytes_per_element)
The ratio is static (per compiled shader); a peeled loop copy repeats numerator and denominator alike.
"""
import collections, csv, re, sys

USE = {'0': 'A', '1': 'B', '2': 'Accumulator'}
SIZE = {'half': 2, 'float': 4, 'char': 1, 'uchar': 1, 'int': 4, 'uint': 4, 'short': 2, 'ushort': 2}


def const(tok, consts):
    tok = tok.lstrip('%')
    if tok in consts:
        return consts[tok]
    m = re.match(r'u?int_(\d+)$', tok)
    return m.group(1) if m else tok


def main():
    w = csv.writer(sys.stdout)
    w.writerow(['file', 'record', 'detail', 'count', 'distinct_A', 'distinct_B', 'A_source', 'B_source',
                'loaded_operands', 'loaded_bytes', 'matrix_ops', 'ops_per_loaded_byte', 'local_size'])
    for path in sys.argv[1:]:
        types, consts, rtype, defs, ptr_sc, names = {}, {}, {}, {}, {}, {}
        muladds, local = [], ''
        for line in open(path):
            line = line.split(';')[0].rstrip()
            m = re.match(r'\s*(%\S+) = (Op\w+)\s*(.*)', line)
            if not m:
                e = re.match(r'\s*OpExecutionMode(?:Id)? \S+ LocalSize(?:Id)? (.*)', line)
                if e:
                    local = e.group(1)
                continue
            rid, op, rest = m.group(1), m.group(2), m.group(3).split()
            defs[rid] = (op, rest)
            if op == 'OpConstant':
                consts[rid.lstrip('%')] = rest[1]
            elif op == 'OpTypeFloat':
                names[rid] = {'16': 'half', '32': 'float', '64': 'double'}[rest[0]]
            elif op == 'OpTypeInt':
                names[rid] = {('8', '1'): 'char', ('8', '0'): 'uchar', ('32', '1'): 'int', ('32', '0'): 'uint',
                              ('16', '1'): 'short', ('16', '0'): 'ushort'}.get((rest[0], rest[1]), 'int' + rest[0])
            elif op == 'OpTypeCooperativeMatrixKHR':
                types[rid] = (names.get(rest[0], rest[0]), const(rest[2], consts), const(rest[3], consts),
                              USE.get(const(rest[4], consts), rest[4]))
            elif op == 'OpTypePointer':
                ptr_sc[rid] = rest[0]
            elif op == 'OpCooperativeMatrixMulAddKHR':
                muladds.append((rest[0], rest[1], rest[2], rest[3]))
            if op not in ('OpConstant', 'OpTypeFloat', 'OpTypeInt', 'OpTypePointer', 'OpTypeCooperativeMatrixKHR') and rest:
                rtype[rid] = rest[0]
        name = path.split('/')[-1].replace('.spvasm', '')
        for rid, t in types.items():
            w.writerow([name, 'OpTypeCooperativeMatrixKHR', f'{t[0]} {t[1]}x{t[2]} use={t[3]}'] + [''] * 10)

        def tname(i):
            t = types.get(rtype.get(i))
            return f'{t[0]} {t[1]}x{t[2]} {t[3]}' if t else 'unknown'

        def source(i, depth=0):
            op, rest = defs.get(i, ('?', []))
            if op == 'OpCooperativeMatrixLoadKHR':
                p = rest[1]
                while p in defs and defs[p][0] in ('OpAccessChain', 'OpInBoundsAccessChain', 'OpPtrAccessChain'):
                    p = defs[p][1][1]
                pt = rtype.get(p)
                return 'load:' + ptr_sc.get(pt, defs.get(p, ('?', ['?', '?']))[1][1] if defs.get(p, ('?',))[0] == 'OpVariable' else '?')
            if op in ('OpPhi', 'OpCopyObject') and depth < 4:
                return op + '>' + source(rest[1], depth + 1)
            return op

        sig = collections.Counter()
        for res, a, b, c in muladds:
            t = types.get(res)
            sig[f'A[{tname(a)}] x B[{tname(b)}] + C[{tname(c)}] -> {t[0]} {t[1]}x{t[2]} {t[3]}'] += 1
        da = sorted({a for _, a, _, _ in muladds}); db = sorted({b for _, _, b, _ in muladds})
        loaded = [i for i in da + db if source(i).startswith('load')]
        lbytes = 0
        for i in loaded:
            t = types[rtype[i]]
            lbytes += int(t[1]) * int(t[2]) * SIZE[t[0]]
        ops = 0
        for res, a, b, c in muladds:
            ta, tb = types[rtype[a]], types[rtype[b]]
            ops += 2 * int(ta[1]) * int(ta[2]) * int(tb[2])   # 2 * M * K * N per multiply-add
        for s, n in sig.items():
            w.writerow([name, 'OpCooperativeMatrixMulAddKHR', s, n, len(da), len(db),
                        '/'.join(sorted({source(i) for i in da})), '/'.join(sorted({source(i) for i in db})),
                        len(loaded), lbytes, ops, f'{ops / lbytes:.2f}' if lbytes else '', local])


main()
