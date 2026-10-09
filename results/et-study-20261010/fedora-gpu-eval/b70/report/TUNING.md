# Intel(R) Graphics (BMG G31) shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 11385 | 13742 | 14338 | 17196 | 16196 |
| vec2 | 11397 | 11408 | 14610 | 11178 | 20300 |
| vec4 | 11409 | 14221 | 11311 | 19170 | 19049 |

- Fastest: vec2 × 16 chains, WG 256: 20300 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 16, vec4 → 8. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 26816 | 30534 | 30929 | 36087 | 37226 |
| vec2 | 39890 | 38901 | 39434 | 39318 | 18251 |
| vec4 | 42868 | 35198 | 33200 | 13855 | 17684 |

- Fastest: vec4 × 1 chains, WG 256: 42868 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 603.9 | — |

- Best: vec4 (16 B per access), WG 128: 603.9 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): read 603.7, write 511.5, copy 534.0, triad 479.1. Writes reach only 85% of reads: coalesce output into wide stores.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 128 MiB (best 13844 GB/s vs DRAM 604 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 10019 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 13844 GB/s; ratio 0.72×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 10019, 32: 2742 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~85 ns for small working sets, ~296 ns at 256 MiB.
- Little's law: saturating DRAM needs ~178 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 42868, alu_fp32 20300, dot_int8 50366, matrix_fp16 173326, matrix_fp16_fp32 179886, matrix_int8 359865.
- fp16 is 2.11× fp32: worth it for compute-bound kernels.
- int8 dot4 (8 ops each) runs at 1.17× fp16 FMA throughput.

