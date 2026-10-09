# ExecuTorch kernels on the AMD Radeon 780M Graphics (RADV PHOENIX) roofline

Source: `/home/doremy/Desktop/sarc-acl/.artifacts/roofline-et-study/runs/dev/780m/linear-r1.json` (ExecuTorch device: amd radeon 780m graphics (radv phoenix), group size 128).

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
| llama-3.1-8b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×4096 | 181399.0 | 0.38 | 1628 | compute | 3% | 3% | 4% |
| llama-3.1-8b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×4096 | 162596.0 | 0.42 | 1628 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×1024 | 41635.4 | 0.41 | 743 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×1024 | 37750.6 | 0.46 | 743 | compute | 4% | 4% | 4% |
| llama-3.1-8b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×4096×14336 | 657146.0 | 0.37 | 2274 | compute | 3% | 3% | 3% |
| llama-3.1-8b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×4096×14336 | 585137.0 | 0.41 | 2274 | compute | 4% | 4% | 4% |
| llama-3.1-8b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×14336×4096 | 670772.0 | 0.36 | 2274 | compute | 3% | 3% | 3% |
| llama-3.1-8b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×14336×4096 | 603982.0 | 0.40 | 2274 | compute | 4% | 4% | 4% |
| llama-3.1-8b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×4096 | 102.3 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.1-8b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×4096 | 105.6 | 0.32 | 4 | memory | 95% | 4% | — |
| llama-3.1-8b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×1024 | 36.0 | 0.23 | 4 | memory | 70% | 3% | — |
| llama-3.1-8b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×1024 | 37.4 | 0.22 | 4 | memory | 67% | 3% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×4096×14336 | 350.6 | 0.33 | 4 | memory | 100% | 4% | — |
| llama-3.1-8b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×4096×14336 | 348.2 | 0.34 | 4 | memory | 100% | 4% | — |
| llama-3.1-8b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×14336×4096 | 380.2 | 0.31 | 4 | memory | 92% | 4% | — |
| llama-3.1-8b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×14336×4096 | 385.8 | 0.30 | 4 | memory | 91% | 4% | — |
| llama-3.2-3b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×3072 | 98378.6 | 0.39 | 1287 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×3072 | 89299.2 | 0.43 | 1287 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×1024 | 30937.2 | 0.42 | 700 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×1024 | 28048.8 | 0.46 | 700 | compute | 4% | 4% | 4% |
| llama-3.2-3b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×3072×8192 | 275616.0 | 0.37 | 1744 | compute | 3% | 3% | 3% |
| llama-3.2-3b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×3072×8192 | 247960.0 | 0.42 | 1744 | compute | 4% | 4% | 4% |
| llama-3.2-3b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×8192×3072 | 277149.0 | 0.37 | 1744 | compute | 3% | 3% | 3% |
| llama-3.2-3b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×8192×3072 | 246790.0 | 0.42 | 1744 | compute | 4% | 4% | 4% |
| llama-3.2-3b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×3072 | 62.6 | 0.30 | 4 | memory | 90% | 4% | — |
| llama-3.2-3b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×3072 | 61.7 | 0.31 | 4 | memory | 91% | 4% | — |
| llama-3.2-3b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×1024 | 30.7 | 0.21 | 4 | memory | 61% | 3% | — |
| llama-3.2-3b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×1024 | 32.3 | 0.19 | 4 | memory | 58% | 2% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×3072×8192 | 153.3 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.2-3b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×3072×8192 | 152.2 | 0.33 | 4 | memory | 99% | 4% | — |
| llama-3.2-3b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×3072 | 160.1 | 0.31 | 4 | memory | 94% | 4% | — |
| llama-3.2-3b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×3072 | 158.8 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.2-1b | wq_wo | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×2048 | 41074.1 | 0.42 | 907 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wq_wo | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×2048 | 37382.9 | 0.46 | 907 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wk_wv | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×512 | 9351.3 | 0.46 | 390 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wk_wv | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×512 | 8777.4 | 0.49 | 390 | compute | 4% | 4% | 5% |
| llama-3.2-1b | w1_w3 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×2048×8192 | 178497.0 | 0.38 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w1_w3 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×2048×8192 | 159749.0 | 0.43 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w2 | 4w | prefill | texture3d | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half` | 2048×8192×2048 | 178161.0 | 0.39 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | w2 | 4w | prefill | buffer | linear | `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_buffer_texture2d_half` | 2048×8192×2048 | 161051.0 | 0.43 | 1358 | compute | 4% | 4% | 4% |
| llama-3.2-1b | wq_wo | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×2048 | 34.0 | 0.25 | 4 | memory | 74% | 3% | — |
| llama-3.2-1b | wq_wo | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×2048 | 33.8 | 0.25 | 4 | memory | 74% | 3% | — |
| llama-3.2-1b | wk_wv | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×512 | 19.1 | 0.11 | 4 | memory | 33% | 1% | — |
| llama-3.2-1b | wk_wv | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×512 | 21.7 | 0.10 | 4 | memory | 29% | 1% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×2048×8192 | 102.6 | 0.33 | 4 | memory | 97% | 4% | — |
| llama-3.2-1b | w1_w3 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×2048×8192 | 102.0 | 0.33 | 4 | memory | 98% | 4% | — |
| llama-3.2-1b | w2 | 4w | decode | texture3d | linear | `linear_q4gsw_coop_texture3d_texture2d_half` | 1×8192×2048 | 106.4 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.2-1b | w2 | 4w | decode | buffer | linear | `linear_q4gsw_coop_buffer_texture2d_half` | 1×8192×2048 | 106.0 | 0.32 | 4 | memory | 94% | 4% | — |
| llama-3.1-8b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×4096 | 8434.0 | 8.15 | 2030 | compute | 57% | 57% | 58% |
| llama-3.1-8b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×4096 | 8423.8 | 8.16 | 2030 | compute | 57% | 57% | 58% |
| llama-3.1-8b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×1024 | 2235.1 | 7.69 | 1163 | compute | 53% | 53% | 54% |
| llama-3.1-8b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×1024 | 2220.5 | 7.74 | 1163 | compute | 54% | 54% | 55% |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×4096×14336 | 29237.9 | 8.23 | 2468 | compute | 57% | 57% | 58% |
| llama-3.1-8b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×4096×14336 | 29011.5 | 8.29 | 2468 | compute | 58% | 58% | 59% |
| llama-3.1-8b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×14336×4096 | 32257.5 | 7.46 | 3146 | compute | 52% | 52% | 53% |
| llama-3.1-8b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×14336×4096 | 32199.5 | 7.47 | 3146 | compute | 52% | 52% | 53% |
| llama-3.1-8b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×4096 | 102.3 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.1-8b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×4096 | 106.4 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×1024 | 36.0 | 0.23 | 4 | memory | 70% | 2% | — |
| llama-3.1-8b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×1024 | 38.8 | 0.22 | 4 | memory | 65% | 2% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×4096×14336 | 350.2 | 0.34 | 4 | memory | 100% | 3% | — |
| llama-3.1-8b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×4096×14336 | 348.9 | 0.34 | 4 | memory | 100% | 3% | — |
| llama-3.1-8b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×14336×4096 | 380.3 | 0.31 | 4 | memory | 92% | 3% | — |
| llama-3.1-8b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×14336×4096 | 386.0 | 0.30 | 4 | memory | 91% | 3% | — |
| llama-3.2-3b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×3072 | 4792.9 | 8.06 | 1626 | compute | 56% | 56% | 57% |
| llama-3.2-3b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×3072 | 4763.2 | 8.12 | 1626 | compute | 56% | 56% | 57% |
| llama-3.2-3b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×1024 | 1668.2 | 7.72 | 1062 | compute | 54% | 54% | 55% |
| llama-3.2-3b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×1024 | 1655.1 | 7.78 | 1062 | compute | 54% | 54% | 55% |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×3072×8192 | 12535.0 | 8.22 | 1950 | compute | 57% | 57% | 58% |
| llama-3.2-3b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×3072×8192 | 12423.2 | 8.30 | 1950 | compute | 58% | 58% | 59% |
| llama-3.2-3b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×8192×3072 | 13102.2 | 7.87 | 2433 | compute | 55% | 55% | 56% |
| llama-3.2-3b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×8192×3072 | 13092.4 | 7.87 | 2433 | compute | 55% | 55% | 56% |
| llama-3.2-3b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×3072 | 62.8 | 0.30 | 4 | memory | 90% | 3% | — |
| llama-3.2-3b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×3072 | 61.7 | 0.31 | 4 | memory | 91% | 3% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×1024 | 30.7 | 0.20 | 4 | memory | 61% | 2% | — |
| llama-3.2-3b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×1024 | 31.1 | 0.20 | 4 | memory | 61% | 2% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×3072×8192 | 153.5 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-3b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×3072×8192 | 153.0 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-3b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×3072 | 159.9 | 0.31 | 4 | memory | 94% | 3% | — |
| llama-3.2-3b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×3072 | 159.4 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.2-1b | wq_wo | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×2048 | 2185.3 | 7.86 | 1163 | compute | 55% | 55% | 56% |
| llama-3.2-1b | wq_wo | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×2048 | 2166.2 | 7.93 | 1163 | compute | 55% | 55% | 56% |
| llama-3.2-1b | wk_wv | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×512 | 577.5 | 7.44 | 627 | compute | 52% | 52% | 53% |
| llama-3.2-1b | wk_wv | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×512 | 570.8 | 7.52 | 627 | compute | 52% | 52% | 53% |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×2048×8192 | 8481.9 | 8.10 | 1479 | compute | 56% | 56% | 57% |
| llama-3.2-1b | w1_w3 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×2048×8192 | 8407.0 | 8.17 | 1479 | compute | 57% | 57% | 58% |
| llama-3.2-1b | w2 | 8da4w | prefill | texture3d | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_texture3d_texture2d_half` | 2048×8192×2048 | 8934.3 | 7.69 | 2031 | compute | 53% | 53% | 54% |
| llama-3.2-1b | w2 | 8da4w | prefill | buffer | linear | `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_t128x64k32g42s32_buffer_texture2d_half` | 2048×8192×2048 | 8934.5 | 7.69 | 2031 | compute | 53% | 53% | 54% |
| llama-3.2-1b | wq_wo | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×2048 | 31.7 | 0.26 | 4 | memory | 79% | 2% | — |
| llama-3.2-1b | wq_wo | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×2048 | 32.4 | 0.26 | 4 | memory | 77% | 2% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×512 | 20.2 | 0.10 | 4 | memory | 31% | 1% | — |
| llama-3.2-1b | wk_wv | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×512 | 21.9 | 0.10 | 4 | memory | 29% | 1% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×2048×8192 | 102.6 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-1b | w1_w3 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×2048×8192 | 102.5 | 0.33 | 4 | memory | 98% | 3% | — |
| llama-3.2-1b | w2 | 8da4w | decode | texture3d | linear | `linear_dq8ca_q4gsw_coop_texture3d_texture2d_half_zpint8` | 1×8192×2048 | 106.2 | 0.32 | 4 | memory | 94% | 3% | — |
| llama-3.2-1b | w2 | 8da4w | decode | buffer | linear | `linear_dq8ca_q4gsw_coop_buffer_texture2d_half_zpint8` | 1×8192×2048 | 105.9 | 0.32 | 4 | memory | 94% | 3% | — |
