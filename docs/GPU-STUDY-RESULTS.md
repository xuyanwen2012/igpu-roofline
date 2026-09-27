# GPU roofline and ExecuTorch study results

Recorded studies now cover five GPUs. Each report preserves its own device,
driver, quantization, correctness and timing conditions; these are not a single
matched cross-device benchmark campaign.

| GPU | Roofline-guided shader results | Full-model evidence |
|---|---|---|
| Radeon 780M | [Tuning and lessons](780M-WMMA-LESSONS.md) | [Four-GPU model study](WMMA-STUDY-TAKEAWAYS.md) |
| Intel Arc Pro B70 | [Xe2 tuning and lessons](XE2-WMMA-LESSONS.md#arc-pro-b70-bmg-g31) | [Four-GPU model study](WMMA-STUDY-TAKEAWAYS.md) |
| Intel Arc B580 | [Xe2 tuning and lessons](XE2-WMMA-LESSONS.md) | [Four-GPU model study](WMMA-STUDY-TAKEAWAYS.md) |
| NVIDIA RTX 4070 Ti SUPER | [Tuning and lessons](4070TI-WMMA-LESSONS.md) | [Four-GPU model study](WMMA-STUDY-TAKEAWAYS.md) |
| NVIDIA Jetson Orin Nano 8 GB (`orin-naughty`) | [Roofs, tuning and lessons](JETSON-WMMA-LESSONS.md) | 1B/3B repeated prefill comparisons; 8B projection checks, but full-model comparison remains unestablished |

The Jetson study used 15 W mode and a 612 MHz GPU maximum without changing
power or clock settings. It did not compare the other Jetson's available memory.
Its final 8B probe stopped on 1 MiB of additional system swap while about
2.1 GiB remained available; this does not establish an OOM or hardware fit limit.

Jetson uses a different prompt fixture and separately recorded source versions
from the four-GPU model study. Consult each report before comparing absolute
throughput. Microkernel, whole-operator and model speedups are distinct metrics.
