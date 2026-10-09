# Intel(R) Arc(tm) B580 Graphics (BMG G21) supplementary measurements

## Load-to-use latency (pointer chasing)

One invocation follows a host-built chain `j = next[j]`; every load depends on the previous one. Each dispatch walks the whole chain (2^16..2^20 loads); latency is the differential per-load time (fixed dispatch cost removed), in ns (clocks are not pinned unless the report says so).

| working set (random, 64 B nodes) | latency ns |
|---:|---:|
| 1024 KiB | 84.6 |
| 4096 KiB | 84.7 |
| 16384 KiB | 102.8 |
| 65536 KiB | 258.4 |
| 262144 KiB | 298.0 |

![latency](latency.png)
