# NVIDIA GeForce RTX 4070 Ti SUPER shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 23198 | 30051 | 43024 | 44412 | 41206 |
| vec2 | 23568 | 41482 | 43970 | 23126 | 22869 |
| vec4 | 26746 | 28125 | 24054 | 23110 | 25838 |

- Fastest: vec1 × 8 chains, WG 128: 44412 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 4, vec2 → 2, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 23216 | 44972 | 43684 | 44641 | 41031 |
| vec2 | 32194 | 36644 | 38858 | 40269 | 41651 |
| vec4 | 32085 | 36196 | 38412 | 40075 | 41265 |

- Fastest: vec1 × 2 chains, WG 256: 44972 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 2, vec2 → 16, vec4 → 16. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 3125.8 | — |

- Best: vec4 (16 B per access), WG 128: 3125.8 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 646.0, read 712.5, triad 632.3, write 641.8.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 256 MiB (best 12453 GB/s vs DRAM 662 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 21080 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 12453 GB/s; ratio 1.69×.
- Shared memory is clearly faster than the cache: staging reused data in shared memory pays off.
- Independent accumulators vs shared read bandwidth: 8: 21080, 32: 18530 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~92 ns for small working sets, ~206 ns at 256 MiB.
- Little's law: saturating DRAM needs ~147 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 44972, alu_fp32 44412, dot_int8 77900, matrix_fp16 182962, matrix_fp16_fp32 92808, matrix_int8 371152.
- fp16 is 1.01× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 1.73× fp16 FMA throughput.

