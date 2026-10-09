# AMD Radeon 780M Graphics (RADV PHOENIX) shader tuning guide

Generated from this device's measurements (subgroup 64, max shared 65536 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 3437 | 4437 | 5548 | 5901 | 5916 |
| vec2 | 3416 | 3364 | 3470 | 3577 | 3390 |
| vec4 | 2629 | 3036 | 3284 | 3207 | 3264 |

- Fastest: vec1 × 16 chains, WG 128: 5916 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 4, vec2 → never, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 3431 | 4248 | 4544 | 4633 | 4734 |
| vec2 | 8244 | 8130 | 7944 | 7428 | 7636 |
| vec4 | 8119 | 6117 | 6567 | 6790 | 6398 |

- Fastest: vec2 × 1 chains, WG 128: 8244 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 86.5 | — |

- Best: vec4 (16 B per access), WG 128: 86.5 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 71.4, read 86.7, triad 73.0, write 77.3.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 32 MiB (best 3465 GB/s vs DRAM 86 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 2272 GB/s (sharedbw_fp32_v2_op0_acc32, WG 256); cache-reuse read 3465 GB/s; ratio 0.66×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 2233, 32: 2272 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~141 ns for small working sets, ~176 ns at 256 MiB.
- Little's law: saturating DRAM needs ~15 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 8244, alu_fp32 5916, dot_int8 11872, matrix_fp16 10947, matrix_fp16_fp32 14801, matrix_int8 14402.
- fp16 is 1.39× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 1.44× fp16 FMA throughput.

