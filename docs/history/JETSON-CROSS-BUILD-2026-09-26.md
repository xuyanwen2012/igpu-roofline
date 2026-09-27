# Fedora → Jetson ExecuTorch: verified 2026-09-26

Cross-compilation and device execution succeeded for Llama 3.2 1B Vulkan **4w and
8da4w** on `duck-naughty` (Orin Nano 8GB, L4T 39.2.1 / JetPack 7.2.1,
NVIDIA Vulkan 595.78). GPU UUID: `b49259c9-868c-5b7c-b6f1-65a2bf4b63be`.

[Reproduction recipe](../../tools/jetson-cross/README.md) uses rootless Podman on
Fedora with an x86_64 Ubuntu 24.04 image, GCC AArch64 cross compiler and Vulkan
SDK 1.4.341.1. No target emulation, CUDA build or on-device compilation is needed.
This is a custom image, not a claim that NVIDIA publishes a JetPack 7.2 image.

## Source and fixes

ExecuTorch revision: `0270403ba53ea4b3c4671b8037d468bdeb0f8d8b`, copied through clean
git archives with its recorded submodules. Other agents' dirty source files were
excluded; the original checkout was not edited. Two isolated patches are recorded:

1. Restore four SDPA decode `_coop` shader files from `8ff908a36^`. The branch's
   cleanup deleted them while runtime dispatch still used them. Initial generation
   aborted after the first token with missing
   `sdpa_compute_attn_weights_coop_buffer_buffer_half`; the original failed log is
   retained. Restoring these files fixes the existing packaging regression.
2. Enable and link ETDump in the separately configured `llama_main` CMake project.
   The core tracing option alone did not enable the runner's compile-time guard.

## Validation

| Check | 4w | 8da4w |
|---|---|---|
| Default/tiled full-model generation, normal prompt | Passed | Passed |
| Small microkernel numerical correctness | Passed | Passed |
| Four 1B production shapes, M=2048, sampled CPU reference | All passed | All passed |
| Explicit WMMA full-model prefill and decode | Passed | Passed |
| ETDump confirms intended WMMA kernel | 112 events | 112 events |

The initial eight successful checks took about 47 seconds of controller wall time;
the four full-model trace checks took another 14 seconds, excluding build and
transfer. This is not an hours-long device campaign.

Actual prefill kernels, from full-model ETDump delegate events:

- 4w: `linear_q4gsw_coopmat_tsweep_dbuf4_t128x128k16g22s32_texture3d_texture2d_half`
- 8da4w: `linear_dq8ca_q4gsw_coopmat_tsweep_dbuf4zpgtr_mk32_t128x128k32g44s32_texture3d_texture2d_half`

Each WMMA trace also contains 784 texture `_coop` linear decode events, plus the
buffer linear path. The restored SDPA decode shader executes successfully. Default
traces show tiled prefill instead of coopmat. These are actual dispatch records,
not merely selected environment variables.

## Scope and evidence

Small correctness and sampled production-shape checks validate the exercised
microkernels. They do not establish exhaustive correctness or whole-model numerical
parity. WMMA smoke uses a repetitive 256-token prompt; default generation uses a
normal prompt. Prompt lengths differ, so these runs cannot support a tiled-versus-
WMMA speedup claim. Clocks were not pinned; cold timings are diagnostic only.
No clocks, power settings, system libraries or services were changed.

Local ignored artifacts under `out/jetson-cross/` retain the image ID, source and
patch manifest, tool versions, model hashes, ARM64 bundle, build logs, original
failure, successful validation logs, four ETDump files and parsed dispatch counts.
Key paths: `logs/validation/`, `logs/validation-trace/`, `traces/`,
`dispatch-summary.json`, `bundle-sha256.txt`. These require the original workspace;
the recipe and this report are versionable evidence of the procedure and outcome.
