# ExecuTorch kernels on the Intel(R) Arc(tm) B580 Graphics (BMG G21) roofline

Source: `/home/doremy/Desktop/sarc-acl/.artifacts/roofline-et-study/runs/dev/b580/linear-r1.json` (ExecuTorch device: intel(r) arc(tm) b580 graphics (bmg g21), group size 128).

Ops = 2·M·N·K (integer ops for 8da4w). Bytes = compulsory traffic (int4 weights + fp16 scales + inputs + fp16 output, each once), so intensity is an upper bound. Attainable = min(compute roof, intensity × DRAM read roof). Only confirmed roofs with repeat spread ≤ 5 % are used.

## Roofs used

| roof | confirmed median | unit | repeat spread |
|---|---:|---|---:|
| alu_fp16 | 27.295 | TFLOP/s | 0.0% |
| dot_int8 | 32.060 | TOP/s | 0.0% |
| global_read | 465.231 | GB/s | 0.0% |

## Kernels

| model | layer | scheme | regime | storage | suite | kernel | M×K×N | µs | TOP/s | ops/B | bound | % attainable | % compute roof | % shared-fed MMA |
|---|---|---|---|---|---|---|---|---:|---:|---:|---|---:|---:|---:|
| llama-3.1-8b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×4096×4096 | 9952.9 | 6.90 | 1628 | compute | 25% | 25% | — |
| llama-3.1-8b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×4096×4096 | 12008.4 | 5.72 | 1628 | compute | 21% | 21% | — |
| llama-3.1-8b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×4096×1024 | 2670.4 | 6.43 | 743 | compute | 24% | 24% | — |
| llama-3.1-8b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×4096×1024 | 3264.9 | 5.26 | 743 | compute | 19% | 19% | — |
| llama-3.1-8b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×4096×14336 | 42794.9 | 5.62 | 2274 | compute | 21% | 21% | — |
| llama-3.1-8b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×4096×14336 | 42352.6 | 5.68 | 2274 | compute | 21% | 21% | — |
| llama-3.1-8b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×14336×4096 | 46947.5 | 5.12 | 2274 | compute | 19% | 19% | — |
| llama-3.1-8b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×14336×4096 | 43012.9 | 5.59 | 2274 | compute | 20% | 20% | — |
| llama-3.1-8b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×4096 | 47.7 | 0.70 | 4 | memory | 39% | 3% | — |
| llama-3.1-8b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×4096 | 44.9 | 0.75 | 4 | memory | 41% | 3% | — |
| llama-3.1-8b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×1024 | 23.6 | 0.36 | 4 | memory | 20% | 1% | — |
| llama-3.1-8b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×1024 | 20.4 | 0.41 | 4 | memory | 23% | 2% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×14336 | 211.3 | 0.56 | 4 | memory | 31% | 2% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×14336 | 202.9 | 0.58 | 4 | memory | 32% | 2% | — |
| llama-3.1-8b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×14336×4096 | 227.0 | 0.52 | 4 | memory | 29% | 2% | — |
| llama-3.1-8b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×14336×4096 | 224.5 | 0.52 | 4 | memory | 29% | 2% | — |
| llama-3.2-3b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×3072×3072 | 6998.7 | 5.52 | 1287 | compute | 20% | 20% | — |
| llama-3.2-3b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×3072×3072 | 6845.9 | 5.65 | 1287 | compute | 21% | 21% | — |
| llama-3.2-3b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×3072×1024 | 2656.9 | 4.85 | 700 | compute | 18% | 18% | — |
| llama-3.2-3b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×3072×1024 | 2447.9 | 5.26 | 700 | compute | 19% | 19% | — |
| llama-3.2-3b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×3072×8192 | 20208.3 | 5.10 | 1744 | compute | 19% | 19% | — |
| llama-3.2-3b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×3072×8192 | 18000.6 | 5.73 | 1744 | compute | 21% | 21% | — |
| llama-3.2-3b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×8192×3072 | 15922.3 | 6.47 | 1744 | compute | 24% | 24% | — |
| llama-3.2-3b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×8192×3072 | 18344.4 | 5.62 | 1744 | compute | 21% | 21% | — |
| llama-3.2-3b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×3072 | 30.2 | 0.62 | 4 | memory | 35% | 2% | — |
| llama-3.2-3b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×3072 | 28.8 | 0.66 | 4 | memory | 36% | 2% | — |
| llama-3.2-3b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×1024 | 15.8 | 0.40 | 4 | memory | 22% | 1% | — |
| llama-3.2-3b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×1024 | 14.4 | 0.44 | 4 | memory | 24% | 2% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×8192 | 78.2 | 0.64 | 4 | memory | 36% | 2% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×8192 | 69.0 | 0.73 | 4 | memory | 41% | 3% | — |
| llama-3.2-3b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×3072 | 70.3 | 0.72 | 4 | memory | 40% | 3% | — |
| llama-3.2-3b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×3072 | 66.1 | 0.76 | 4 | memory | 42% | 3% | — |
| llama-3.2-1b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×2048×2048 | 2536.4 | 6.77 | 907 | compute | 25% | 25% | — |
| llama-3.2-1b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×2048×2048 | 3074.6 | 5.59 | 907 | compute | 20% | 20% | — |
| llama-3.2-1b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×2048×512 | 726.4 | 5.91 | 390 | compute | 22% | 22% | — |
| llama-3.2-1b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×2048×512 | 833.1 | 5.16 | 390 | compute | 19% | 19% | — |
| llama-3.2-1b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×2048×8192 | 9810.0 | 7.01 | 1358 | compute | 26% | 26% | — |
| llama-3.2-1b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×2048×8192 | 11937.0 | 5.76 | 1358 | compute | 21% | 21% | — |
| llama-3.2-1b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_tiled_texture3d_texture2d_half` | 2048×8192×2048 | 10257.9 | 6.70 | 1358 | compute | 25% | 25% | — |
| llama-3.2-1b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_tiled_buffer_texture2d_half` | 2048×8192×2048 | 12313.7 | 5.58 | 1358 | compute | 20% | 20% | — |
| llama-3.2-1b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×2048 | 21.9 | 0.38 | 4 | memory | 21% | 1% | — |
| llama-3.2-1b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×2048 | 16.6 | 0.50 | 4 | memory | 28% | 2% | — |
| llama-3.2-1b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×512 | 12.3 | 0.17 | 4 | memory | 10% | 1% | — |
| llama-3.2-1b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×512 | 11.3 | 0.19 | 4 | memory | 10% | 1% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×8192 | 51.4 | 0.65 | 4 | memory | 36% | 2% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×8192 | 45.6 | 0.74 | 4 | memory | 41% | 3% | — |
| llama-3.2-1b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×2048 | 49.7 | 0.68 | 4 | memory | 38% | 2% | — |
| llama-3.2-1b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×2048 | 46.9 | 0.72 | 4 | memory | 40% | 3% | — |
| llama-3.1-8b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×4096×4096 | 2913.2 | 23.59 | 2030 | compute | 74% | 74% | — |
| llama-3.1-8b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×4096×4096 | 3082.3 | 22.30 | 2030 | compute | 70% | 70% | — |
| llama-3.1-8b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×4096×1024 | 785.6 | 21.87 | 1163 | compute | 68% | 68% | — |
| llama-3.1-8b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×4096×1024 | 834.8 | 20.58 | 1163 | compute | 64% | 64% | — |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×4096×14336 | 14348.9 | 16.76 | 2468 | compute | 52% | 52% | — |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×4096×14336 | 14843.5 | 16.20 | 2468 | compute | 51% | 51% | — |
| llama-3.1-8b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×14336×4096 | 14273.2 | 16.85 | 3146 | compute | 53% | 53% | — |
| llama-3.1-8b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×14336×4096 | 14837.7 | 16.21 | 3146 | compute | 51% | 51% | — |
| llama-3.1-8b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×4096 | 47.5 | 0.71 | 4 | memory | 39% | 2% | — |
| llama-3.1-8b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×4096 | 44.8 | 0.75 | 4 | memory | 42% | 2% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×1024 | 17.8 | 0.47 | 4 | memory | 26% | 1% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×1024 | 18.0 | 0.47 | 4 | memory | 26% | 1% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×14336 | 210.8 | 0.56 | 4 | memory | 31% | 2% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×14336 | 203.2 | 0.58 | 4 | memory | 32% | 2% | — |
| llama-3.1-8b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×14336×4096 | 225.6 | 0.52 | 4 | memory | 29% | 2% | — |
| llama-3.1-8b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×14336×4096 | 225.8 | 0.52 | 4 | memory | 29% | 2% | — |
| llama-3.2-3b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×3072×3072 | 1708.2 | 22.63 | 1626 | compute | 71% | 71% | — |
| llama-3.2-3b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×3072×3072 | 1794.0 | 21.55 | 1626 | compute | 67% | 67% | — |
| llama-3.2-3b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×3072×1024 | 603.6 | 21.35 | 1062 | compute | 67% | 67% | — |
| llama-3.2-3b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×3072×1024 | 626.8 | 20.56 | 1062 | compute | 64% | 64% | — |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×3072×8192 | 5532.3 | 18.63 | 1950 | compute | 58% | 58% | — |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×3072×8192 | 5785.6 | 17.82 | 1950 | compute | 56% | 56% | — |
| llama-3.2-3b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×8192×3072 | 4796.4 | 21.49 | 2433 | compute | 67% | 67% | — |
| llama-3.2-3b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×8192×3072 | 5531.6 | 18.63 | 2433 | compute | 58% | 58% | — |
| llama-3.2-3b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×3072 | 29.6 | 0.64 | 4 | memory | 35% | 2% | — |
| llama-3.2-3b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×3072 | 28.4 | 0.66 | 4 | memory | 37% | 2% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×1024 | 18.3 | 0.34 | 4 | memory | 19% | 1% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×1024 | 14.2 | 0.44 | 4 | memory | 25% | 1% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×8192 | 79.0 | 0.64 | 4 | memory | 35% | 2% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×8192 | 66.2 | 0.76 | 4 | memory | 42% | 2% | — |
| llama-3.2-3b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×3072 | 80.6 | 0.62 | 4 | memory | 35% | 2% | — |
| llama-3.2-3b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×3072 | 67.1 | 0.75 | 4 | memory | 42% | 2% | — |
| llama-3.2-1b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×2048×2048 | 726.1 | 23.66 | 1163 | compute | 74% | 74% | — |
| llama-3.2-1b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×2048×2048 | 774.5 | 22.18 | 1163 | compute | 69% | 69% | — |
| llama-3.2-1b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×2048×512 | 221.4 | 19.40 | 627 | compute | 61% | 61% | — |
| llama-3.2-1b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×2048×512 | 232.6 | 18.46 | 627 | compute | 58% | 58% | — |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×2048×8192 | 2846.6 | 24.14 | 1479 | compute | 75% | 75% | — |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×2048×8192 | 3030.2 | 22.68 | 1479 | compute | 71% | 71% | — |
| llama-3.2-1b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_tiled_texture3d_texture2d_half_zpint8` | 2048×8192×2048 | 3039.6 | 22.61 | 2031 | compute | 71% | 71% | — |
| llama-3.2-1b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_tiled_buffer_texture2d_half_zpint8` | 2048×8192×2048 | 3193.1 | 21.52 | 2031 | compute | 67% | 67% | — |
| llama-3.2-1b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×2048 | 16.7 | 0.50 | 4 | memory | 28% | 2% | — |
| llama-3.2-1b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×2048 | 16.3 | 0.52 | 4 | memory | 29% | 2% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×512 | 10.3 | 0.20 | 4 | memory | 11% | 1% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×512 | 11.1 | 0.19 | 4 | memory | 11% | 1% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×8192 | 49.7 | 0.67 | 4 | memory | 38% | 2% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×8192 | 44.3 | 0.76 | 4 | memory | 42% | 2% | — |
| llama-3.2-1b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×2048 | 49.3 | 0.68 | 4 | memory | 38% | 2% | — |
| llama-3.2-1b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×2048 | 46.6 | 0.72 | 4 | memory | 40% | 2% | — |
