# Mali-G710 shader tuning guide

Generated from this device's measurements (subgroup 16, max shared 32768 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | — | 282 | 391 | 585 | 710 |
| vec2 | — | — | 393 | 714 | 703 |
| vec4 | — | 359 | 715 | 686 | 647 |

- Fastest: vec4 × 4 chains, WG 256: 715 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 16, vec2 → 8, vec4 → 4. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 362 | — | — | 390 | 739 |
| vec2 | 516 | 716 | 837 | 1472 | 1395 |
| vec4 | 684 | — | 1445 | 1409 | 1370 |

- Fastest: vec2 × 8 chains, WG 256: 1472 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 8, vec4 → 4. Keep at least this many independent accumulators per thread (vector components count as chains).

- DRAM bandwidth by kernel (GB/s): copy 62.3, triad 43.7, write 42.5.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 16 MiB (best 191 GB/s vs DRAM 59 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 63 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 191 GB/s; ratio 0.33×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 63, 32: 30 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~168 ns for small working sets, ~182 ns at 0.00390625 MiB.

## Precision and data type
- Peaks (G ops/s): alu_fp16 1472, alu_fp32 715, dot_int8 1225.
- fp16 is 2.06× fp32: worth it for compute-bound kernels.
- int8 dot4 (8 ops each) runs at 0.83× fp16 FMA throughput.

