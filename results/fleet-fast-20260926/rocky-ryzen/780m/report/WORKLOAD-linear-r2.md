# ExecuTorch kernels on the AMD Radeon 780M Graphics (RADV PHOENIX) roofline

Source: `/home/doremy/Desktop/sarc-acl/.artifacts/roofline-et-study/runs/dev/780m/linear-r2.json` (ExecuTorch device: amd radeon 780m graphics (radv phoenix), group size 128).

Ops = 2·M·N·K (integer ops for 8da4w). Bytes = compulsory traffic (int4 weights + fp16 scales + inputs + fp16 output, each once), so intensity is an upper bound. Attainable = min(compute roof, intensity × DRAM read roof). Only confirmed roofs with repeat spread ≤ 5 % are used.

## Roofs used

| roof | confirmed median | unit | repeat spread |
|---|---:|---|---:|
| alu_fp16 | 8.136 | TFLOP/s | 3.2% |
| dot_int8 | 11.717 | TOP/s | 1.4% |
| global_read | 86.672 | GB/s | 0.1% |
| matrix_fp16 | 10.958 | TFLOP/s | 0.1% |
| matrix_fp16_feed_shared | 10.784 | TFLOP/s | 0.3% |
| matrix_int8 | 14.393 | TOP/s | 0.2% |
| matrix_int8_feed_shared | 14.140 | TOP/s | 0.2% |

## Kernels

| model | layer | scheme | regime | storage | suite | kernel | M×K×N | µs | TOP/s | ops/B | bound | % attainable | % compute roof | % shared-fed MMA |
|---|---|---|---|---|---|---|---|---:|---:|---:|---|---:|---:|---:|
| llama-3.1-8b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×4096 | 180380.0 | 0.38 | 1628 | compute | 3% | 3% | 4% |
| llama-3.1-8b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×4096 | 162646.0 | 0.42 | 1628 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×1024 | 41564.5 | 0.41 | 743 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×1024 | 37943.1 | 0.45 | 743 | compute | 4% | 4% | 4% |
| llama-3.1-8b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×14336 | 660646.0 | 0.36 | 2274 | compute | 3% | 3% | 3% |
| llama-3.1-8b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×14336 | 584347.0 | 0.41 | 2274 | compute | 4% | 4% | 4% |
| llama-3.1-8b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×14336×4096 | 670316.0 | 0.36 | 2274 | compute | 3% | 3% | 3% |
| llama-3.1-8b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×14336×4096 | 604023.0 | 0.40 | 2274 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×4096 | 102.5 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.1-8b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×4096 | 105.6 | 0.32 | 4 | memory | 95% | 4% | — |
| llama-3.1-8b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×1024 | 36.7 | 0.23 | 4 | memory | 68% | 3% | — |
| llama-3.1-8b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×1024 | 37.9 | 0.22 | 4 | memory | 66% | 3% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×14336 | 351.0 | 0.33 | 4 | memory | 100% | 4% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×14336 | 348.2 | 0.34 | 4 | memory | 100% | 4% | — |
| llama-3.1-8b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×14336×4096 | 380.4 | 0.31 | 4 | memory | 92% | 4% | — |
| llama-3.1-8b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×14336×4096 | 385.7 | 0.30 | 4 | memory | 91% | 4% | — |
| llama-3.2-3b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×3072 | 98718.0 | 0.39 | 1287 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×3072 | 89312.2 | 0.43 | 1287 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×1024 | 30901.0 | 0.42 | 700 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×1024 | 27876.2 | 0.46 | 700 | compute | 4% | 4% | 4% |
| llama-3.2-3b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×8192 | 277825.0 | 0.37 | 1744 | compute | 3% | 3% | 3% |
| llama-3.2-3b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×8192 | 246938.0 | 0.42 | 1744 | compute | 4% | 4% | 4% |
| llama-3.2-3b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×8192×3072 | 277111.0 | 0.37 | 1744 | compute | 3% | 3% | 3% |
| llama-3.2-3b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×8192×3072 | 248296.0 | 0.42 | 1744 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×3072 | 62.8 | 0.30 | 4 | memory | 90% | 4% | — |
| llama-3.2-3b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×3072 | 60.6 | 0.31 | 4 | memory | 93% | 4% | — |
| llama-3.2-3b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×1024 | 32.0 | 0.20 | 4 | memory | 59% | 2% | — |
| llama-3.2-3b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×1024 | 31.4 | 0.20 | 4 | memory | 60% | 2% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×8192 | 153.4 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×8192 | 152.2 | 0.33 | 4 | memory | 99% | 4% | — |
| llama-3.2-3b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×3072 | 160.2 | 0.31 | 4 | memory | 94% | 4% | — |
| llama-3.2-3b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×3072 | 158.8 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.2-1b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×2048 | 41255.9 | 0.42 | 907 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×2048 | 37311.9 | 0.46 | 907 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×512 | 9336.4 | 0.46 | 390 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×512 | 8746.3 | 0.49 | 390 | compute | 4% | 4% | 5% |
| llama-3.2-1b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×8192 | 178756.0 | 0.38 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×8192 | 160165.0 | 0.43 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×8192×2048 | 179090.0 | 0.38 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×8192×2048 | 162354.0 | 0.42 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×2048 | 33.9 | 0.25 | 4 | memory | 74% | 3% | — |
| llama-3.2-1b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×2048 | 34.4 | 0.24 | 4 | memory | 73% | 3% | — |
| llama-3.2-1b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×512 | 20.0 | 0.10 | 4 | memory | 31% | 1% | — |
| llama-3.2-1b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×512 | 21.8 | 0.10 | 4 | memory | 29% | 1% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×8192 | 102.8 | 0.33 | 4 | memory | 97% | 4% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×8192 | 102.1 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.2-1b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×2048 | 106.4 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.2-1b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×2048 | 106.2 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.1-8b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×4096 | 8448.2 | 8.13 | 2030 | compute | 57% | 57% | 58% |
| llama-3.1-8b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×4096 | 8424.7 | 8.16 | 2030 | compute | 57% | 57% | 58% |
| llama-3.1-8b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×1024 | 2232.8 | 7.69 | 1163 | compute | 53% | 53% | 54% |
| llama-3.1-8b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×1024 | 2221.6 | 7.73 | 1163 | compute | 54% | 54% | 55% |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×14336 | 29228.1 | 8.23 | 2468 | compute | 57% | 57% | 58% |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×14336 | 29105.0 | 8.26 | 2468 | compute | 57% | 57% | 58% |
| llama-3.1-8b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×14336×4096 | 32271.0 | 7.45 | 3146 | compute | 52% | 52% | 53% |
| llama-3.1-8b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×14336×4096 | 32247.8 | 7.46 | 3146 | compute | 52% | 52% | 53% |
| llama-3.1-8b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×4096 | 102.6 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.1-8b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×4096 | 106.4 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×1024 | 35.7 | 0.24 | 4 | memory | 70% | 2% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×1024 | 38.0 | 0.22 | 4 | memory | 66% | 2% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×14336 | 350.3 | 0.34 | 4 | memory | 100% | 3% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×14336 | 348.9 | 0.34 | 4 | memory | 100% | 3% | — |
| llama-3.1-8b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×14336×4096 | 380.4 | 0.31 | 4 | memory | 92% | 3% | — |
| llama-3.1-8b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×14336×4096 | 386.4 | 0.30 | 4 | memory | 91% | 3% | — |
| llama-3.2-3b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×3072 | 4797.8 | 8.06 | 1626 | compute | 56% | 56% | 57% |
| llama-3.2-3b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×3072 | 4768.5 | 8.11 | 1626 | compute | 56% | 56% | 57% |
| llama-3.2-3b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×1024 | 1668.8 | 7.72 | 1062 | compute | 54% | 54% | 55% |
| llama-3.2-3b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×1024 | 1658.3 | 7.77 | 1062 | compute | 54% | 54% | 55% |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×8192 | 12533.2 | 8.22 | 1950 | compute | 57% | 57% | 58% |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×8192 | 12452.4 | 8.28 | 1950 | compute | 58% | 58% | 59% |
| llama-3.2-3b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×8192×3072 | 13108.0 | 7.86 | 2433 | compute | 55% | 55% | 56% |
| llama-3.2-3b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×8192×3072 | 13109.4 | 7.86 | 2433 | compute | 55% | 55% | 56% |
| llama-3.2-3b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×3072 | 63.0 | 0.30 | 4 | memory | 90% | 3% | — |
| llama-3.2-3b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×3072 | 62.1 | 0.30 | 4 | memory | 91% | 3% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×1024 | 28.3 | 0.22 | 4 | memory | 66% | 2% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×1024 | 32.2 | 0.20 | 4 | memory | 58% | 2% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×8192 | 153.5 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×8192 | 152.9 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-3b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×3072 | 160.1 | 0.31 | 4 | memory | 94% | 3% | — |
| llama-3.2-3b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×3072 | 159.4 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.2-1b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×2048 | 2185.2 | 7.86 | 1163 | compute | 55% | 55% | 56% |
| llama-3.2-1b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×2048 | 2168.6 | 7.92 | 1163 | compute | 55% | 55% | 56% |
| llama-3.2-1b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×512 | 576.6 | 7.45 | 627 | compute | 52% | 52% | 53% |
| llama-3.2-1b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×512 | 570.2 | 7.53 | 627 | compute | 52% | 52% | 53% |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×8192 | 8473.3 | 8.11 | 1479 | compute | 56% | 56% | 57% |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×8192 | 8411.4 | 8.17 | 1479 | compute | 57% | 57% | 58% |
| llama-3.2-1b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×8192×2048 | 8934.9 | 7.69 | 2031 | compute | 53% | 53% | 54% |
| llama-3.2-1b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×8192×2048 | 8930.6 | 7.69 | 2031 | compute | 53% | 53% | 54% |
| llama-3.2-1b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×2048 | 32.8 | 0.26 | 4 | memory | 76% | 2% | — |
| llama-3.2-1b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×2048 | 33.7 | 0.25 | 4 | memory | 75% | 2% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×512 | 20.2 | 0.10 | 4 | memory | 31% | 1% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×512 | 21.6 | 0.10 | 4 | memory | 29% | 1% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×8192 | 102.7 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×8192 | 102.4 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-1b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×2048 | 106.4 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.2-1b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×2048 | 105.9 | 0.32 | 4 | memory | 94% | 3% | — |
