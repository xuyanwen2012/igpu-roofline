#!/usr/bin/env python3
"""Split a RADV_DEBUG=shaders,shaderstats stderr capture into one file per compiled shader that contains
v_wmma instructions. Keeps the `disasm:` section and the `*** SHADER STATS ***` block (as the worked example
in the ExecuTorch tree does). Usage: split_radv_dump.py <stderr file> <out dir> <prefix>
Prints one CSV line per kept shader: file, ordinal of the shader in the capture, and its statistics."""
import re, sys, pathlib

src, out, prefix = sys.argv[1], pathlib.Path(sys.argv[2]), sys.argv[3]
out.mkdir(parents=True, exist_ok=True)
lines = open(src, errors='replace').read().splitlines()
starts = [i for i, l in enumerate(lines) if l.startswith('disasm:')]
stats = [i for i, l in enumerate(lines) if l.startswith('*** SHADER STATS ***')]
KEYS = ['VGPRs', 'SGPRs', 'Spilled VGPRs', 'Spilled SGPRs', 'LDS size', 'Scratch size', 'Subgroups per SIMD', 'Code size', 'Instructions', 'Pre-Sched SGPRs', 'Pre-Sched VGPRs']
print('file,ordinal,' + ','.join(k.replace(' ', '_') for k in KEYS) + ',wmma_total')
kept = 0
for n, a in enumerate(starts):
    s = next(i for i in stats if i > a)
    e = s + 1
    while e < len(lines) and re.match(r'^[A-Za-z][A-Za-z \-]*: ', lines[e]):
        e += 1
    body = lines[a:e]
    wm = sum(1 for l in body if re.match(r'\s*v_wmma_', l))
    if not wm:
        continue
    kept += 1
    st = dict(l.split(': ', 1) for l in lines[s + 1:e] if ': ' in l)
    name = f'{prefix}-shader{n + 1:02d}.isa.txt'
    (out / name).write_text(f'; RADV (ACO) disassembly, shader {n + 1} of {len(starts)} in {pathlib.Path(src).name}\n' + '\n'.join(body) + '\n')
    print(','.join([name, str(n + 1)] + [st.get(k, '') for k in KEYS] + [str(wm)]))
