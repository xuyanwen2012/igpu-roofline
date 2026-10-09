// REQUIRED_SUBGROUP_SIZE = 16
/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the BSD-style license found in the
 * LICENSE file in the root directory of this source tree.
 */

/*
 * SARC development zone: sweep twin of glsl/sarc/sarc_linear_q4gsw_coopmat.glsl.
 * From the version directive on, this file must stay byte-identical to that
 * one (checked by sarc/tools/check.sh); only the template name (this file
 * name) and the variant list in the yaml differ.
 */

#version 450 core

#extension GL_KHR_cooperative_matrix : require
#extension GL_KHR_memory_scope_semantics : require
#extension GL_KHR_shader_subgroup_basic : enable
#extension GL_EXT_shader_explicit_arithmetic_types : require
#extension GL_EXT_shader_explicit_arithmetic_types_float16 : require
#extension GL_EXT_control_flow_attributes : enable

#define PRECISION highp



#define IO_TEXTURE

// ACC_GROUP_FP32 (RTX 4070 Ti SUPER, 2026-09-26): accumulate each quantization
// group in fp16 at the full fp16 MMA rate, then add it into an fp32 total and
// restart, so an fp16 run never exceeds one group. The GeForce fp16-accumulate
// MMA loses accuracy over long K (8B w2, K = 14336: max |err| 1.49, over the
// 0.5 tolerance; already 0.45 at K = 4096); with this, 0.08 / 0.04. Plain fp32
// accumulation (0.04) runs at half the tensor rate: 0.63x vs 0.92x speed.

// ACC_GROUP_FP32_REG (Adreno 840, 2026-09-28): ACC_GROUP_FP32 with the fp32
// total held per invocation in registers instead of an fp32 accumulator
// coopmat, which Adreno does not expose (fp16 MMA is fp16 -> fp16 only).

layout(std430) buffer;

#include "common.glslh"

layout(set = 0, binding = 0, rgba16f) uniform PRECISION restrict writeonly image3D t_output;
layout(set = 0, binding = 1) uniform PRECISION sampler3D t_input;
layout(set = 0, binding = 2, rgba32i) uniform PRECISION restrict readonly iimage2D t_packed_weight;

layout(set = 0, binding = 3) buffer PRECISION restrict readonly t_weight_scalesBuffer {
    f16vec4 t_weight_scales[];
};


layout(set = 0, binding = 4) buffer PRECISION restrict readonly t_biasBuffer {
    float16_t t_bias[];
};



layout(set = 0, binding = 5) uniform PRECISION restrict readonly output_sizes_UBO {
  ivec4 output_sizes;
};

layout(set = 0, binding = 6) uniform PRECISION restrict readonly input_sizes_UBO {
  ivec4 input_sizes;
};

layout(local_size_x_id = 0, local_size_y_id = 1, local_size_z_id = 2) in;

layout(constant_id = 3) const int apply_bias = 0;
layout(constant_id = 4) const int K4_per_group = 0;
layout(constant_id = 5) const int num_groups_arg = 0;
layout(constant_id = 6) const int out_N_arg = 0;


// Accumulator element type. ACC_FP32 (RDNA3, 780M roofline study 2026-09-26):
// v_wmma_f16_16x16x16_f16 takes/returns one fp16 per VGPR, so a packed
// coopmat<float16_t> accumulator is repacked with v_mov_b16 around every WMMA
// (~350 moves per 32 WMMAs in the t128x128k32g42s32 loop); the fp32
// accumulator maps 1:1 onto v_wmma_f32_16x16x16_f16. Roofline: matrix
// fp16->fp32 14.77 vs fp16->fp16 10.96 TFLOP/s on the 780M.
#if defined(ACC_FP32) && defined(ACC_GROUP_FP32)
#error "ACC_FP32 (fp32 accumulate) and ACC_GROUP_FP32 (fp16 per group, fp32 total) are exclusive"
#endif
#if defined(ACC_GROUP_FP32_REG) && (defined(ACC_FP32) || defined(ACC_GROUP_FP32))
#error "ACC_GROUP_FP32_REG (fp32 total in registers) excludes ACC_FP32 and ACC_GROUP_FP32"
#endif
#ifdef ACC_FP32
#define ACC_T float
#else
#define ACC_T float16_t
#endif







#define FRAG_LAYOUT


#define IMG_W

// --- Tile geometry (from yaml; per-variant tile-sweep candidate) ---
const uint MMA_M = 8;
const uint MMA_N = 16;
const uint MMA_K = 16;

const uint WG_TILE_M = 128;
const uint WG_TILE_N = 128;
const uint WG_TILE_K = 32;

const uint SG_GRID_X = 8;
const uint SG_GRID_Y = 4;
const uint SUBGROUP_SIZE = 16;

#include "sarc_linear_q4gsw_coopmat_body.glslh"
