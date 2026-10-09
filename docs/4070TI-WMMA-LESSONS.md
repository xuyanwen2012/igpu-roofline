# RTX 4070 Ti SUPER WMMA tuning: results and lessons (2026-09-26)

Roofline- and profiler-driven tuning of the ExecuTorch Vulkan prefill microkernels on the
NVIDIA GeForce RTX 4070 Ti SUPER (AD103, driver 615.71.09, host gpu-dev-4004):
- 8da4w: `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr`.
- 4w: `linear_q4gsw_coopmat_tsweep_dbuf4`.

Scope set by the owner: `test_llama_microbench` prefill microkernels only. See
[780M-WMMA-LESSONS.md](780M-WMMA-LESSONS.md) and [XE2-WMMA-LESSONS.md](XE2-WMMA-LESSONS.md)
for the other GPUs.

- ExecuTorch branch `yanwen/release14-quant-shaders-4070ti`, on top of `be54d12db`:
  - `1eb8dc705` test tooling;
  - `d4e86b465` default-on coopmat and the 8da4w tile;
  - `0270403ba` per-shape 4w tiles;
  - `432709b92` per-group fp32 accumulation for 4w (correctness fix).
  Only "4070 ti super" devices change.
- Roofs: `results/fleet-fast-20260926/gpu-dev-4004/4070tis` (fast plan, automatic clocks).
- Raw runs, profiles and tools live in `sarc-acl/.artifacts/roofline-et-study/`:
  - `runs/4070ti-branch` (before), `runs/4070ti-final2` (after, with `COMPARE.md`);
  - `screen/`;
  - nsys reports on gpu-dev-4004 under `~/.cache/et-roofline-study/nsys/`;
  - `tools/vkpipestats.cpp`.
  All measurement-only shader code (phase timing, ablations, negative variants) is
  archived in `4070ti-8da4w-exploration-all.patch`.

## Result

Defaults only (no `ET_VK_*` overrides). Workload: Llama 3.2 1B / 3.2 3B / 3.1 8B prefill
(M = 2048), 3 repeats each of `--linear` and forced-tiled `--baseline`; every WMMA cell is
within 4 % repeat spread. Checks:
- `--correctness-only`: 10/10 runs clean.
- Sampled production-shape diff: all 1B/3B/8B shapes, both schemes, both storages (see
  "Open issue" for the one exception).

| 4070 Ti prefill | vs previous branch kernels | WMMA / tiled | % of matching matrix roof |
|---|---:|---:|---:|
| 8da4w texture3d (model path) | **1.34×** (1.26–1.47) | 6.66× → **8.99×** | 28–32 % → 37–42 % (int8, 369 TOP/s) |
| 8da4w buffer | **2.12×** (2.04–2.28) | 3.83× → 8.18× | 16–18 % → 34–40 % |
| 4w texture3d (model path) | 1.04× tiles, then 0.92× for the accuracy fix | 9.77× → **9.01×** | 54–67 % (fp16, 184 TFLOP/s) |
| 4w buffer | 1.13× tiles, then 0.87× for the accuracy fix | 7.45× → **6.48×** | 46–58 % |

Deployment effect: before, the branch ran tiled kernels unless `ET_VK_COOPMAT_ANY_DEVICE=1`
was set. Coopmat is now on by default on this device (`ET_VK_COOPMAT_ANY_DEVICE=0` turns it
off), so the default model path is ~9× faster in these microkernels.

## Profiling on NVIDIA Vulkan (what works)

| Tool | Gives | Notes |
|---|---|---|
| `sudo nsys profile --gpu-metrics-set=ad10x --gpu-metrics-frequency=50000 --trace=vulkan` | Tensor Active, SM Issue, warps in flight, DRAM read/write, GPC clock per 20 µs | Headless over ssh. Counters need root (`ERR_NVGPUCTRPERM` otherwise). Average the samples inside each long `VULKAN_WORKLOAD` range (sqlite export). |
| `vkpipestats` (`VK_KHR_pipeline_executable_properties`) | Register count, binary size, local memory (low 32 bits), shared memory | Compiles only, never dispatches. No SASS: the pipeline cache blob is compressed or encrypted (entropy ≈7.9 bit/byte). NVIDIA results are therefore **not ISA-verified**. |
| Differential ablation (mask one loop stage per variant) | Time share of each stage under the real schedule | The decisive tool here. Results are wrong by design; timing only. |
| In-kernel `clock2x32ARB` phase timing | — | **Do not use on NVIDIA**: the clock reads blocked instruction scheduling and doubled the kernel time. It worked on the 780M. |

Two derived metrics were useful:
- **Tensor Active vs roof fraction**: nsys Tensor Active matched the roofline fraction
  (≈30 % for the old 8da4w, ≈73 % for 4w).
- **SM Issue ÷ Tensor Active**: this is instructions issued per unit of tensor work. It
  exposed compiler code-generation differences that timing alone could not.

## 8da4w: what changed (and why)

Starting point: `mk32_t128x128k32g44s32` (16 warps × 2×2 int8 16×16×32 MMAs per k32 chunk,
one 512-thread workgroup per SM). Its profile:
- Tensor Active 30 %, SM Issue 30 %, DRAM < 8 %, clock not throttled. Nothing was
  saturated: a latency/serialization problem.
- Arithmetic check: per chunk, the int8 MMA work is ≈490 SM-cycles. That is half of 4w's
  ≈980 cycles, for the same bytes staged, so the MMAs could not cover the staging.

Ablations of the k64 kernel (3B wq_wo, 301 µs full):

| Stage removed | Time saved |
|---|---:|
| A int8 `coopMatStore` into LDS | 82 µs (27 %) |
| Barrier | 50 µs |
| A global `coopMatLoad` | 47 µs |
| B global fetch | 16 µs |
| B dequant + LDS store | 16 µs |
| (MMA only, no staging) | runs at 272 TOP/s, 74 % of roof |

| Change | Evidence | Effect |
|---|---|---|
| `WG_TILE_K` 32 → 64 | MMA phase too short to hide staging; roofline LDS-fed int8 = 366–369 TOP/s at any reuse, so LDS→MMA is not the limit | buffer 1.85×, texture3d 1.10× |
| `A_RAW`: A staged as raw uvec4 (one 16 B global load + one 16 B LDS store per thread; `Ash` is a uvec4 array) | largest ablation item was the int8 `coopMatStore` | texture3d 303 → 252 µs |
| `B_PAIR`: one weight texel feeds both nibble parities (columns c and c + 4) | old map fetched each 16 B texel 8× to use 4 B | half the fetches and prefetch registers; lane order keeps stores on 32 banks |
| `CSH_IN_ASH` (from the 780M) | texture drain buffer pushed k64 over 48 KiB | lets the k64 tile run with texture IO |

## 8da4w: what did not help (all measured)

| Attempt | Result | Lesson |
|---|---|---|
| Replace runtime `v[c]` vector indexing (local memory, 48 B/thread) with selects | buffer 1.11×, **texture3d 0.65×** | NVIDIA code generation flips on thresholds. The slow variants issued 1.65× more instructions per MMA (SM Issue / Tensor Active) and had 35 % larger binaries. "Remove local memory" is not automatically a win. |
| `STORE_FIRST` (barrier → store previous loads → load next → MMA) | 4–11 % slower | — |
| 256-thread k64 tiles (2 workgroups per SM) | ≈275 µs vs 252 | — |
| 8-MMA-per-warp tiles (207–224 registers) | ≈275 µs | — |
| uvec4 LDS stores alone | 256 → 252 µs | The A store cost was really exposed global-load latency. |

## 4w: what changed

The 4w kernel was already at 70–76 % Tensor Active on the large shapes. During 4w the clock
drops to 2.3–2.6 GHz at the 285 W power limit; 8da4w stays at 2.7 GHz. Ablations (3B, 3B
tile) found two different limits:
- Large projections (w1_w3): MMA-only runs at 92 % of the fp16 roof. The gap is staging the
  MMAs do not hide (B dequant + store ≈19 %).
- N = 3072 / 1024 projections: MMA-only is as slow as the full kernel. The limit is partial
  workgroup waves (3B wq_wo: 192 workgroups on 132 resident slots ≈ 73 % ceiling).

A 12-tile screen of every projection found:
- **buffer**: `t128x256k16g42` wins every shape with N > 512. It is 1.83× on 8B w2,
  1.28× time-weighted.
- **texture3d**: `t256x128k16g22` on large shapes, `t256x128k16g42` at N = 1024, and the
  default at N = 512.

These became shape rules with alignment checks, replacing the per-model 3B/8B overrides.
Structural options were left for the owner to decide:
- producer/consumer warp specialization, which is portable GLSL but only expected to help
  where matrix and vector units issue independently (NVIDIA, possibly Xe2; not RDNA3);
- a larger `WG_TILE_K` for 4w, which measured slower.

## 4w accuracy fix: per-group fp32 accumulation

The sampled production diff failed 8B `w2` (K = 14336) for 4w on both storages with the fp16
accumulator: max |err| 1.49 against the 0.5 tolerance, and 0.35–0.45 already at K = 4096.

The same data passes on B580 and B70 with fp16 accumulation. Their ISA shows `dpas ... :hf`
accumulators, so the difference is inside the matrix units: Xe2 keeps more precision within
each DPAS step. On GeForce the fp16-accumulate tensor path loses more; this is the likely
explanation, not ISA-verified. 8da4w is unaffected everywhere, because it accumulates each
group in int32 and adds groups in fp32.

| 4070 Ti 4w | max \|err\| 8B w2 (K = 14336) | max \|err\| K = 4096 | speed vs fp16 acc (texture3d / buffer) |
|---|---:|---:|---:|
| fp16 accumulation (before) | 1.49 (fails) | 0.35–0.45 | 1 / 1 |
| **per-group fp32 (`ACC_GROUP_FP32`, shipped)** | **0.08** | 0.04–0.05 | **0.92× / 0.87×** |
| plain fp32 accumulation | 0.04 | 0.02–0.03 | 0.63× / 0.67× (half-rate fp16→fp32 MMA) |

How `ACC_GROUP_FP32` works: each 128-K quantization group accumulates in fp16 at full rate,
then the group sum is added into an fp32 total and the fp16 accumulator restarts. The cost is
the extra accumulator registers, not the adds, so it needs smaller per-warp tiles.

Tiles (screen of every projection):
- texture3d: `t256x128k16g42` when M % 256 == 0 and N > 512, else `t128x128k16g24`;
- buffer: `t128x256k16g42` when N % 256 == 0 and N > 512, else `t128x128k16g42`.

Every 4w dispatch on this device uses them.

A measurement mistake worth recording: ComfyUI was restored between milestones and ran jobs
during the first attempt at these timings. The unchanged tiled baseline got up to 2×
slower. Those rows are in `superseded/comfyui-contended/`. The numbers above come from a
rerun with the service stopped and no other compute process on the GPU.

## End-to-end result and a bug the microbench missed

End-to-end `llama_main` prefill (2048 tokens, tiled → tuned, same binary):
- 4w: 3.57× / 4.30× / 5.11× for 1B / 3B / 8B (8B: 880 → 4501 tokens/s).
- 8da4w: 3.11× / 3.78× / 4.54× (8B: 1108 → 5032 tokens/s).

See [WMMA-STUDY-TAKEAWAYS.md](WMMA-STUDY-TAKEAWAYS.md) and `results/e2e-20260926/`.

The end-to-end correctness check found that **8da4w produced garbage for every prompt length that is not
a multiple of 128**. The activation layout (row-major `kPackedInt8_4W`) is fixed at graph build, but
`pick_linear_dqa_qw_shader` re-runs on each resize and fell back to the tiled kernel, which reads the
4h4w layout.
- Fixed in `6fa64bf74`: keep coopmat whenever the activations are row-major.
- The same bug was in the dev branch default on AMD (`d529bfc7b`).
- The microbench (M = 2048) and the timing prompt are aligned, and the microbench data had zero-valued
  activation zero points (now covered by `--production-diff-nonzero-zp`).

## Lessons (in addition to the 780M and Xe2 lessons)

1. Divide per-chunk MMA cycles by the staging cost before tuning. int8 MMA is 2× fp16, so
   an 8da4w tile needs twice the K per barrier of a 4w tile to hide the same staging.
2. On NVIDIA Vulkan, use nsys GPU metrics + pipeline statistics + ablation. Kernel-internal
   clocks perturb scheduling. Read SM Issue ÷ Tensor Active to catch code-generation changes.
3. An ablation that removes a store also removes the wait on the load that feeds it. Confirm
   with a variant that keeps the work but changes only its width (here: uvec4 stores).
4. When the MMA-only ablation is as slow as the full kernel, the limit is outside the loop:
   check workgroup waves against resident slots before touching the loop.
5. ExecuTorch's `gen_vulkan_spv.py` collects descriptors from every `^layout\(set` line,
   ignoring `#ifdef`. A conditional alias binding must use another spelling
   (`layout(std430, set = 0, binding = N)`) or every variant gets an extra descriptor and
   crashes.
6. `--production-diff` must use the exported model's rank-3 layout: rank 2 bypassed the
   shape-keyed tile selection and validated only the default tile.
7. The same declared accumulator type is not the same accuracy on different vendors. Check
   long-K production shapes per device, and print the error margin, not only pass/fail:
   the fp16 4w kernel passed at K = 4096 with 90 % of its tolerance used.
8. Keep co-tenant GPU services stopped until the last timing run on that device, and record
   `nvidia-smi --query-compute-apps` before and after each run.
