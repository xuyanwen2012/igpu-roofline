#!/usr/bin/env python3
"""Count matrix and memory instructions in ACO disassembly (RADV), total and per loop body.

Usage: count_isa.py <file.isa.txt>...   prints CSV.
Extends the worked example (ExecuTorch openspec sarc-1.5-e2e-benchmark/contrib/7900xtx/isa/count_wmma.py):
same loop detection (a backward s_branch/s_cbranch to an earlier BB label closes a loop body), and in
addition LDS loads/stores by mnemonic, barriers, scratch (spill) accesses and the wave size seen in the
exec-mask registers. "loop" rows are the innermost loop bodies that contain at least one v_wmma.
"""
import collections, csv, re, sys

LABEL = re.compile(r'^\s*(BB\d+):')
BRANCH = re.compile(r'\bs_(?:cbranch_\w+|branch)\s+(BB\d+)')
OP = re.compile(r'^\s*([a-z][a-z0-9_]+)\b')
KEEP = re.compile(r'^(v_wmma_\w+|ds_(?:load|read|store|write)\w*|s_barrier\w*|scratch_\w+|v_readlane\w*|v_writelane\w*|global_load\w*|buffer_load\w*|global_store\w*|buffer_store\w*|image_\w+)$')


def ops(lines):
    c = collections.Counter()
    for l in lines:
        m = OP.match(l.split(';')[0])
        if m and KEEP.match(m.group(1)):
            c[m.group(1)] += 1
    return c


def main():
    w = csv.writer(sys.stdout)
    w.writerow(['file', 'scope', 'opcode', 'count'])
    for path in sys.argv[1:]:
        name = path.split('/')[-1]
        lines = open(path, errors='replace').read().splitlines()
        text = '\n'.join(lines)
        blocks, cur = collections.OrderedDict(entry=[]), 'entry'
        for l in lines:
            m = LABEL.match(l)
            if m:
                cur = m.group(1); blocks[cur] = []
            else:
                blocks[cur].append(l)
        names = list(blocks); pos = {n: i for i, n in enumerate(names)}
        for op, n in sorted(ops(lines).items()):
            w.writerow([name, 'total', op, n])
        w.writerow([name, 'total', 'invalid_instruction_lines', text.count('(invalid instruction)')])
        w.writerow([name, 'total', 'wave', 'wave64' if re.search(r'\bs_\w+_b64\b.*exec|exec_hi', text) else 'wave32' if 'exec_lo' in text else 'unknown'])
        loops = []
        for i, n in enumerate(names):
            for l in blocks[n]:
                m = BRANCH.search(l)
                if m and m.group(1) in pos and pos[m.group(1)] <= i:
                    loops.append((pos[m.group(1)], i))
        wm = [(a, b) for a, b in loops if any(k.startswith('v_wmma') for k in ops(x for n in names[a:b + 1] for x in blocks[n]))]
        inner = [(a, b) for a, b in wm if not any((c, d) != (a, b) and a <= c and d <= b for c, d in wm)]
        for a, b in sorted(set(inner)):
            body = [x for n in names[a:b + 1] for x in blocks[n]]
            for op, n in sorted(ops(body).items()):
                w.writerow([name, f'loop {names[a]}..{names[b]}', op, n])


main()
