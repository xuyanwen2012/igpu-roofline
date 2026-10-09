# AMD Radeon 780M Graphics (RADV PHOENIX) shader tuning guide

Generated from this device's measurements (subgroup 64, max shared 65536 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 3433 | 4387 | 5448 | 5718 | 5743 |
| vec2 | 3358 | 3300 | 3444 | 3506 | 3349 |
| vec4 | 2624 | 2982 | 3231 | 3161 | 3174 |

- Fastest: vec1 × 16 chains, WG 256: 5743 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 4, vec2 → never, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 3426 | 4163 | 4451 | 4528 | 4631 |
| vec2 | 8028 | 7947 | 7768 | 7255 | 7425 |
| vec4 | 7888 | 6045 | 6372 | 6627 | 6251 |

- Fastest: vec2 × 1 chains, WG 128: 8028 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 86.4 | — |

- Best: vec4 (16 B per access), WG 128: 86.4 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): read 86.7, write 77.6, copy 71.5, triad 73.1.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 32 MiB (best 3420 GB/s vs DRAM 86 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 2273 GB/s (sharedbw_fp32_v2_op0_acc32, WG 256); cache-reuse read 3420 GB/s; ratio 0.66×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 2249, 32: 2273 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~141 ns for small working sets, ~176 ns at 256 MiB.
- Little's law: saturating DRAM needs ~15 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 8028, alu_fp32 5743, dot_int8 11608, matrix_fp16 10937, matrix_fp16_fp32 14764, matrix_int8 14377.
- fp16 is 1.40× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 1.45× fp16 FMA throughput.

