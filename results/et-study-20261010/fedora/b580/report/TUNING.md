# Intel(R) Arc(tm) B580 Graphics (BMG G21) shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 7270 | 8755 | 9118 | 10930 | 10306 |
| vec2 | 7272 | 7279 | 9285 | 7132 | 12911 |
| vec4 | 7279 | 9073 | 7186 | 12188 | 12116 |

- Fastest: vec2 × 16 chains, WG 256: 12911 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 16, vec4 → 8. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 17297 | 19451 | 19686 | 22952 | 23691 |
| vec2 | 25478 | 24762 | 25082 | 25008 | 11617 |
| vec4 | 27294 | 22391 | 21100 | 8808 | 11247 |

- Fastest: vec4 × 1 chains, WG 256: 27294 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 459.6 | — |

- Best: vec4 (16 B per access), WG 128: 459.6 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 406.2, write 403.2, triad 393.7, read 465.3.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 128 MiB (best 8804 GB/s vs DRAM 460 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 7260 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 8804 GB/s; ratio 0.82×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 7260, 32: 1629 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~85 ns for small working sets, ~298 ns at 256 MiB.
- Little's law: saturating DRAM needs ~139 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 27294, alu_fp32 12911, dot_int8 32059, matrix_fp16 111726, matrix_fp16_fp32 115686, matrix_int8 231362.
- fp16 is 2.11× fp32: worth it for compute-bound kernels.
- int8 dot4 (8 ops each) runs at 1.17× fp16 FMA throughput.

