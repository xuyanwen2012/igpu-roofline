# NVIDIA GeForce RTX 4070 Ti SUPER shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 23236 | 30048 | 43010 | 44421 | 41176 |
| vec2 | 23569 | 41494 | 43745 | 23121 | 22864 |
| vec4 | 26749 | 28123 | 24053 | 23117 | 25931 |

- Fastest: vec1 × 8 chains, WG 256: 44421 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 4, vec2 → 2, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 23221 | 44975 | 43697 | 44637 | 41033 |
| vec2 | 32195 | 36644 | 38860 | 40273 | 41650 |
| vec4 | 32084 | 36190 | 38413 | 40072 | 41458 |

- Fastest: vec1 × 2 chains, WG 256: 44975 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 2, vec2 → 16, vec4 → 16. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 3141.9 | — |

- Best: vec4 (16 B per access), WG 128: 3141.9 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): read 712.0, copy 646.1, write 642.0, triad 632.1.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 256 MiB (best 12532 GB/s vs DRAM 659 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 21072 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 12532 GB/s; ratio 1.68×.
- Shared memory is clearly faster than the cache: staging reused data in shared memory pays off.
- Independent accumulators vs shared read bandwidth: 8: 21072, 32: 18429 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~92 ns for small working sets, ~206 ns at 256 MiB.
- Little's law: saturating DRAM needs ~147 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 44975, alu_fp32 44421, dot_int8 78046, matrix_fp16 182952, matrix_fp16_fp32 92808, matrix_int8 371142.
- fp16 is 1.01× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 1.74× fp16 FMA throughput.

