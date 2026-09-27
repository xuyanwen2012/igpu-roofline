# Intel(R) Arc(tm) B580 Graphics (BMG G21) shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 7270 | 8753 | 9119 | 10932 | 10310 |
| vec2 | 7276 | 7279 | 9285 | 7132 | 12913 |
| vec4 | 7279 | 9074 | 7187 | 12189 | 12116 |

- Fastest: vec2 × 16 chains, WG 256: 12913 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 16, vec4 → 8. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 17295 | 19451 | 19691 | 22954 | 23691 |
| vec2 | 25463 | 24768 | 25093 | 25005 | 11618 |
| vec4 | 27295 | 22391 | 21103 | 8807 | 11249 |

- Fastest: vec4 × 1 chains, WG 256: 27295 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 461.7 | — |

- Best: vec4 (16 B per access), WG 128: 461.7 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 408.5, read 465.1, triad 391.1, write 396.0.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 128 MiB (best 8795 GB/s vs DRAM 462 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 7259 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 8795 GB/s; ratio 0.83×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 7259, 32: 1628 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~80 ns for small working sets, ~298 ns at 256 MiB.
- Little's law: saturating DRAM needs ~139 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 27295, alu_fp32 12913, dot_int8 32060, matrix_fp16 111672, matrix_fp16_fp32 115684, matrix_int8 231365.
- fp16 is 2.11× fp32: worth it for compute-bound kernels.
- int8 dot4 (8 ops each) runs at 1.17× fp16 FMA throughput.

