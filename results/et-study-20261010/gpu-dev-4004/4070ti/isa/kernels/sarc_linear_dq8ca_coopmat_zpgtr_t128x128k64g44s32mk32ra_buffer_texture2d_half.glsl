// REQUIRED_SUBGROUP_SIZE = 32
/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * All rights reserved.
 *
 * This source code is licensed under the BSD-style license found in the
 * LICENSE file in the root directory of this source tree.
 */

/*
 * SARC dq8ca (8da4w) int8 cooperative-matrix linear, "zpgtr" family: row-major
 * (kPackedInt8_4W) int8 activations staged by coopMatLoad/Store, zp hoisted.
 *
 * Template header only (bindings, spec constants, per-variant tile geometry);
 * the kernel is the untemplated sarc_linear_dq8ca_coopmat_zpgtr_body.glslh, shared with the sweep twin
 * glsl/sarc_dev/sarc_linear_dq8ca_coopmat_zpgtr_sweep.glsl, which must stay byte-identical to this
 * file from the version directive on (sarc/tools/check.sh).
 *
 * Feature defines (yaml parameters, default off):
 *   A_RAW       A staged as raw uvec4 global->LDS copies (GeForce)
 *   B_PAIR      one weight texel feeds both nibble parities
 *   CSH_IN_ASH  texture3d drain band staged in Ash_int8
 */

#version 450 core

#extension GL_KHR_cooperative_matrix : require
#extension GL_KHR_memory_scope_semantics : require
#extension GL_KHR_shader_subgroup_basic : enable
#extension GL_EXT_shader_explicit_arithmetic_types : require
#extension GL_EXT_shader_explicit_arithmetic_types_int8 : require
// 8-bit SSBO access: A is bound as a scalar int8_t array so that the
// coopMatLoad below has a MATCHING component type (see dbuf4tr's header for
// why the type must match on this driver).
#extension GL_EXT_shader_8bit_storage : require
#extension GL_EXT_shader_explicit_arithmetic_types_float16 : require
#extension GL_EXT_control_flow_attributes : enable

#define PRECISION highp

#define WEIGHT_INT4




// RTX 4070 Ti SUPER tuning (2026-09-26). Differential timing (each stage
// removed in turn) and nsys GPU metrics on the 4070 Ti showed the int8 MMA
// loop idle ~70% of the time, dominated by staging rather than by the MMAs.
//
// A_RAW: stage A as raw 16-byte vectors (uvec4 global load -> uvec4 LDS
// store) instead of coopMatLoad(global) -> coopMatStore(LDS). Ash_int8
// becomes a uvec4 array so each store is one 128-bit LDS store. Needs
// WG_TILE_M * WG_TILE_K / 16 to be a multiple of the workgroup size.
#define A_RAW
// B_PAIR: one weight texel fetch feeds both nibble parities of one component
// (output columns c and c + 4): half the fetches and half the prefetch
// registers of the one-uint-per-slot map.
#define B_PAIR
// CSH_IN_ASH: stage the texture-IO drain band in Ash_int8, which is dead after
// the last MMA (every drain iteration starts with a barrier). Frees the
// Csh_out array so a WG_TILE_K = 64 tile fits the 48 KiB shared-memory limit.
// DRAIN_UNROLL: hand-expand the texture-IO drain band loop so every result[][]
// access has a constant index (the loop's barrier() keeps it rolled). Opt-in.
// B_SEL_EARLY_N: B slots si < N select their one int of the fetched texel right
// after the fetch instead of keeping the whole texel live. Opt-in.

layout(std430) buffer;

#include "common.glslh"

// Bindings — match add_linear_dqa_qw_node arg order:
//   output(0), fp_input(1), packed_int8_input(2), int_input_sums(3 - unused),
//   input_scales(4), input_zps(5), packed_weight(6), weight_sums(7),
//   weight_scales(8), bias(9).

layout(set = 0, binding = 0) buffer PRECISION restrict writeonly t_outputBuffer {
    float16_t t_output[];
};

// t_input is unread here -- the activations arrive already quantized in
// t_packed_int8_input -- but stays declared so the binding layout matches the
// dispatch site. It tracks IO_STORAGE so the two IO tensors stay consistent.

layout(set = 0, binding = 1) buffer PRECISION restrict readonly t_inputBuffer {
    f16vec4 t_input[];
};

// ROW-MAJOR (kPackedInt8_4W) packed activations, bound as a scalar int8_t
// array (row stride = K int8) -- dbuf4tr's binding, unchanged. The stock
// 4h4w layout dbuf4zpg uses is NOT row-major (component index selects a row,
// non-affine), so it cannot be addressed by any coopMatLoad.

layout(set = 0, binding = 2) buffer PRECISION restrict readonly t_packed_int8_inputBuffer {
    int8_t t_packed_int8_input[];
};

#ifdef A_RAW
// uvec4 view of binding 2 (t_packed_int8_input) for 16-byte A staging.
// Spelled layout(std430, set...) on purpose: gen_vulkan_spv.py collects the
// descriptor list from every line matching ^layout\(set regardless of #ifdef,
// so the usual spelling would add a 13th descriptor to every variant.
layout(std430, set = 0, binding = 2) buffer restrict readonly t_packed_int8_input_v4Buffer {
  uvec4 t_packed_int8_input_v4[];
};
#endif

layout(set = 0, binding = 3) buffer PRECISION restrict readonly t_int8_input_sumsBuffer {
    int t_int8_input_sums[];
};

layout(set = 0, binding = 4) uniform PRECISION sampler3D t_int8_input_scales;
layout(set = 0, binding = 5) uniform PRECISION isampler3D t_int8_input_zps;
layout(set = 0, binding = 6) uniform PRECISION isampler2D t_packed_weight;

layout(set = 0, binding = 7) buffer PRECISION restrict readonly t_weight_sumsBuffer {
    int t_weight_sums[];
};


layout(set = 0, binding = 8) buffer PRECISION restrict readonly t_weight_scalesBuffer {
    f16vec4 t_weight_scales[];
};


layout(set = 0, binding = 9) buffer PRECISION restrict readonly t_biasBuffer {
    float16_t t_bias[];
};



layout(set = 0, binding = 10) uniform PRECISION restrict readonly output_sizes_UBO {
  ivec4 output_sizes;
};

layout(set = 0, binding = 11) uniform PRECISION restrict readonly input_sizes_UBO {
  ivec4 input_sizes;
};

layout(local_size_x_id = 0, local_size_y_id = 1, local_size_z_id = 2) in;

layout(constant_id = 3) const int apply_bias = 0;
// INT4 only; inert (0) for INT8 so the dispatcher's spec list lines up.
layout(constant_id = 4) const int K4_per_group = 0;
layout(constant_id = 5) const int num_groups_arg = 0;
layout(constant_id = 6) const int out_N_arg = 0;

// Tile geometry
const uint MMA_M = 16;
const uint MMA_N = 16;
const uint MMA_K = 32;

const uint WG_TILE_M = 128;
const uint WG_TILE_N = 128;
const uint WG_TILE_K = 64;

const uint SG_GRID_X = 4;
const uint SG_GRID_Y = 4;
const uint SUBGROUP_SIZE = 32;

#include "sarc_linear_dq8ca_coopmat_zpgtr_body.glslh"
