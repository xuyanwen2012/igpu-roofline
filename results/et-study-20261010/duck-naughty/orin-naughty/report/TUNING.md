# NVIDIA Tegra Orin (nvgpu) shader tuning guide

Generated from this device's measurements (subgroup 32, max shared 49152 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 622 | 805 | 1146 | 1201 | 1111 |
| vec2 | 632 | 623 | 615 | 1135 | 547 |
| vec4 | 712 | 697 | 789 | 560 | 733 |

- Fastest: vec1 × 8 chains, WG 128: 1201 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 4, vec2 → 8, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 618 | 1204 | 1170 | 1193 | 1097 |
| vec2 | 911 | 1100 | 1444 | 1415 | 1764 |
| vec4 | 1028 | 1228 | 1358 | 1529 | 1303 |

- Fastest: vec2 × 16 chains, WG 256: 1764 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → 16, vec4 → never. Keep at least this many independent accumulators per thread (vector components count as chains).

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 62.4 | — |

- Best: vec4 (16 B per access), WG 128: 62.4 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): write 58.1, read 62.2, triad 64.3, copy 64.1.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 64 MiB (best 378 GB/s vs DRAM 58 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 617 GB/s (sharedbw_fp32_v2_op0, WG 64); cache-reuse read 378 GB/s; ratio 1.63×.
- Shared memory is clearly faster than the cache: staging reused data in shared memory pays off.
- Independent accumulators vs shared read bandwidth: 8: 617, 32: 492 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~78 ns for small working sets, ~1052 ns at 4 MiB.
- Little's law: saturating DRAM needs ~65 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 1764, alu_fp32 1201, dot_int8 2090, matrix_fp16 9714, matrix_fp16_fp32 9724, matrix_int8 19516.
- fp16 is 1.47× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 1.18× fp16 FMA throughput.

