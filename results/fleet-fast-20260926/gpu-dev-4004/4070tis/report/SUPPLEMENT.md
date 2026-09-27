# NVIDIA GeForce RTX 4070 Ti SUPER supplementary measurements

## Load-to-use latency (pointer chasing)

One invocation follows a host-built chain `j = next[j]`; every load depends on the previous one. Each dispatch walks the whole chain (2^16..2^20 loads); latency is the differential per-load time (fixed dispatch cost removed), in ns (clocks are not pinned unless the report says so).

| working set (random, 64 B nodes) | latency ns |
|---:|---:|
| 256 KiB | 92.1 |
| 1024 KiB | 100.4 |
| 4096 KiB | 104.6 |
| 16384 KiB | 105.5 |
| 262144 KiB | 206.3 |

![latency](latency.png)
