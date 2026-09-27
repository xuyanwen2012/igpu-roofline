# Samsung Xclipse 940 shader tuning guide

Generated from this device's measurements (subgroup 64, max shared 32768 B). Short-run medians; use them to compare ways of writing a kernel, not as theoretical peaks.

## fp32 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 1586 | 2052 | 2091 | 2348 | 2183 |
| vec2 | 1385 | 2109 | 1908 | 2210 | 2045 |
| vec4 | 1606 | 1905 | 2254 | 1842 | 2029 |

- Fastest: vec1 × 8 chains, WG 128: 2348 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → 8, vec2 → 8, vec4 → 4. Keep at least this many independent accumulators per thread (vector components count as chains).

## fp16 FMA: vector width × independent chains (GFLOP/s, best WG)

| width \ chains | 1 | 2 | 4 | 8 | 16 |
|---|---:|---:|---:|---:|---:|
| vec1 | 2707 | 2710 | 2719 | 2545 | 2727 |
| vec2 | 2499 | 2734 | 2656 | 2506 | 2700 |
| vec4 | 3044 | 2666 | 2555 | 2577 | 2732 |

- Fastest: vec4 × 1 chains, WG 256: 3044 GFLOP/s.
- Independent chains per invocation needed for 90% of that: vec1 → never, vec2 → never, vec4 → 1. Keep at least this many independent accumulators per thread (vector components count as chains).

## Register budget (offline compiler)

- Variants that spill: none.
- Variants below full occupancy: none.
- Live values per thread (width × chains) beyond these cause spills or lower occupancy; size accumulator counts and unroll factors below them.

## DRAM streaming read: vector width × WG (GB/s, >= 256 MiB)

| width | WG 64 | WG 128 | WG 256 |
|---|---:|---:|---:|
| vec1 | — | — | — |
| vec2 | — | — | — |
| vec4 | — | 49.6 | — |

- Best: vec4 (16 B per access), WG 128: 49.6 GB/s; scalar reads reach 0% of it.
- DRAM bandwidth by kernel (GB/s): copy 46.2, read 48.7, triad 54.0, write 55.4.

## Cache working set
- Data re-read within a dispatch stays >= 2× DRAM bandwidth up to 16 MiB (best 1331 GB/s vs DRAM 48 GB/s). Size tiles so the reused set fits in this.

## Shared (workgroup) memory
- Best shared read 560 GB/s (sharedbw_fp32_v2_op0, WG 256); cache-reuse read 1331 GB/s; ratio 0.42×.
- Shared memory is not faster than the cache here: rely on cache locality (bounded working sets, contiguous access) rather than explicit shared-memory staging.
- Independent accumulators vs shared read bandwidth: 8: 560, 32: 436 GB/s. More accumulators no longer help: shared reads are saturated.

## Latency and loads in flight
- Dependent-load latency: ~302 ns for small working sets, ~444 ns at 256 MiB.
- Little's law: saturating DRAM needs ~22 KB of reads in flight GPU-wide (bandwidth × latency). Serial dependent loads (linked structures, indirection chains) are latency-bound; issue independent loads together.

## Precision and data type
- Peaks (G ops/s): alu_fp16 3044, alu_fp32 2348, dot_int8 2314.
- fp16 is 1.30× fp32: little compute gain; the main benefit of fp16 is halving bytes.
- int8 dot4 (8 ops each) runs at 0.76× fp16 FMA throughput.

