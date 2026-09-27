# Mali-G710 shader tuning guide

Generated from this device's measurements (subgroup 16, max shared 32768 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 442 | 468 | 480 | 480 | 487 |
| vec2 | 453 | 482 | 486 | 486 | 477 |
| vec4 | 476 | 485 | 478 | 462 | 435 |

- Fastest: vec1 × 16 chains, WG 256: 487 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 1, vec2 → 1, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 446 | 469 | 480 | 488 | 498 |
| vec2 | 851 | 925 | 953 | 992 | 965 |
| vec4 | 916 | 942 | 974 | 953 | 924 |

- Fastest: vec2 × 8 chains, WG 256: 992 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 2, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 34.9 | — |

- Best: vec4 (16 B per access), WG 128: 34.9 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 58.8, read 33.4, triad 35.7, write 42.3.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 16 MiB (best 180 GB/s vs DRAM 35 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 94 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 180 GB/s; ratio 0.52×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 94, 32: 32 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~150 ns for small working sets, ~150 ns at 0.015625 MiB.
- Little's law: saturating DRAM needs ~5 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 992, alu_fp32 487, dot_int8 1515.
- fp16 is 2.04× fp32: worth it for compute-bound kernels.
- int8 dot4 (8 ops each) runs at 1.53× fp16 FMA throughput.

