// v2 unified runner (replaces main.cpp + sustained.cpp; built as both
// `roofline` and `roofline_sustained`). Timed dispatch batching, compact sample
// output, DEVICE_LOCAL operand buffers with host-visible staging mirrors.
#include <vulkan/vulkan.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <vector>
#include <string>
#include <fstream>
#include <chrono>
#include <algorithm>
#include <numeric>
#include <random>
#include "nlohmann/json.hpp"
#include "context.h"
#include "calibration.h"
using json = nlohmann::json;
static json caps(Ctx &c) {
  // Bind host telemetry to the GPU selected by Vulkan, not the first AMD card.
  json j = {{"gpu", c.props.deviceName},
            {"api_version", c.props.apiVersion},
            {"driver_version", c.props.driverVersion},
            {"timestamp_period_ns", c.props.limits.timestampPeriod},
            {"timestamp_valid_bits", c.timestampBits},
            {"subgroup", g_subgroup},
            {"max_shared_bytes", c.props.limits.maxComputeSharedMemorySize},
            {"max_workgroup_invocations", c.props.limits.maxComputeWorkGroupInvocations},
            {"max_storage_buffer_range", c.props.limits.maxStorageBufferRange}};
  j["device_uuid"] = deviceUUID(c.pd);
  j["vendor_id"] = c.props.vendorID;
  j["device_id"] = c.props.deviceID;
  uint32_t n = 0;
  CHECK(vkEnumerateDeviceExtensionProperties(c.pd, nullptr, &n, nullptr));
  std::vector<VkExtensionProperties> e(n);
  CHECK(vkEnumerateDeviceExtensionProperties(c.pd, nullptr, &n, e.data()));
  j["extensions"] = json::array();
  for (auto &x : e)
    j["extensions"].push_back(x.extensionName);
  auto fn = (PFN_vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR)vkGetInstanceProcAddr(
      c.inst, "vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR");
  bool hasCmExt = false;
  for (auto &x : e)
    if (!strcmp(x.extensionName, "VK_KHR_cooperative_matrix"))
      hasCmExt = true;
  j["matrix_shapes"] = json::array();
  if (fn && hasCmExt) {
    CHECK(fn(c.pd, &n, nullptr));
    std::vector<VkCooperativeMatrixPropertiesKHR> m(n);
    for (auto &x : m)
      x.sType = VK_STRUCTURE_TYPE_COOPERATIVE_MATRIX_PROPERTIES_KHR;
    CHECK(fn(c.pd, &n, m.data()));
    for (auto &x : m)
      j["matrix_shapes"].push_back({{"m", x.MSize},
                                    {"n", x.NSize},
                                    {"k", x.KSize},
                                    {"a", x.AType},
                                    {"b", x.BType},
                                    {"c", x.CType},
                                    {"result", x.ResultType},
                                    {"scope", x.scope},
                                    {"saturating", x.saturatingAccumulation}});
  }
  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
  j["memory_types"] = json::array();
  for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
    j["memory_types"].push_back({{"index", i},
                                 {"flags", mp.memoryTypes[i].propertyFlags},
                                 {"heap", mp.memoryTypes[i].heapIndex}});
  return j;
}
static uint32_t bits(float f) {
  uint32_t x;
  memcpy(&x, &f, 4);
  return x;
}
int main(int argc, char **argv) {
  try {
    const bool identityOnly = argc > 1 && std::string(argv[1]) == "identity";
    Ctx c = createCtx(identityOnly);
    if (identityOnly) {
      puts(json{{"gpu", c.props.deviceName}, {"device_uuid", deviceUUID(c.pd)}}.dump().c_str());
      vkDestroyInstance(c.inst, nullptr);
      return 0;
    }
    if (argc == 1 || std::string(argv[1]) == "capabilities") {
      puts(caps(c).dump().c_str());
      return 0;
    }
    std::ifstream cf(argv[1]);
    json cfg;
    cf >> cfg;
    std::string family = cfg.at("family"), shader = cfg.at("shader");
    uint32_t wg = cfg.value("wg", 64), groups = cfg.value("groups", 256),
             width = cfg.value("width", 1), chains = cfg.value("chains", 1),
             loops = cfg.value("loops", 128), n = cfg.value("n", 1024),
             count = cfg.value("shared_count", 1024), stride = cfg.value("stride", 1),
             op = cfg.value("op", 0);
    std::string dtype = cfg.value("dtype", std::string("fp32")),
                kind = cfg.value("kind", std::string(""));
    uint32_t M = cfg.value("m", 1), N = cfg.value("matrix_n", 1), K = cfg.value("k", 1),
             dots = cfg.value("dots_per_step", 1u), acc = cfg.value("accumulators", 1u),
             flops = cfg.value("flops_per_element", 1u);
    const bool deviceLocal =
        cfg.value("memory_mode", std::string("device_local")) == "device_local";
    const size_t threads = size_t(wg) * groups;
    bool half = dtype == "fp16", integer = dtype == "int8";
    if (family == "matrix" &&
        (!wg || wg % g_subgroup || cfg.value("subgroup", g_subgroup) != g_subgroup))
      throw std::runtime_error("matrix workgroup must contain whole device subgroups");
    const uint32_t subgroups = family == "matrix" ? wg / g_subgroup : 1;
    if (family == "matrix" && half)
      loops = std::min(loops, 1024u / K);
    if (!c.timestampBits || wg > c.props.limits.maxComputeWorkGroupInvocations ||
        groups > c.props.limits.maxComputeWorkGroupCount[0])
      throw std::runtime_error("unsupported launch/timestamps");
    if (family == "shared" &&
        (uint64_t(count) * width * (half ? 2 : 4) > c.props.limits.maxComputeSharedMemorySize ||
         (op && uint64_t(wg) * stride > count)))
      throw std::runtime_error("unsupported shared footprint or nonunique write mapping");
    if (family == "memory" && op == 6 && (wg > 256 || (wg & (wg - 1))))
      throw std::runtime_error("dot reduction needs power-of-two workgroup <= 256");
    size_t sizes[4] = {std::max<size_t>(n * width * 4ull, threads * width * 4),
                       std::max<size_t>(n * width * 4ull, threads * width * 4), 16,
                       std::max<size_t>(n * width * 4ull, threads * width * chains * 4)};
    if (family == "shared")
      sizes[0] = std::max<size_t>(sizes[0], count * width * 4ull);
    if (family == "matrix") {
      const size_t tiles = cfg.contains("feed") ? std::max<uint32_t>(1, n) : 1;
      sizes[0] = tiles * M * K * (integer ? 1 : 2);
      sizes[1] = tiles * K * N * (integer ? 1 : 2);
      sizes[3] = size_t(groups) * subgroups * chains * M * N * (half ? 2 : 4);
      if (sizes[3] > 256ull * 1024 * 1024)
        throw std::runtime_error("matrix output exceeds 256 MiB");
    }
    if (family == "latency") {
      sizes[0] = size_t(n) * 4;
      sizes[1] = 16;
      sizes[3] = 16;
    }
    if (family == "ert") {
      sizes[0] = size_t(n) * 16;
      sizes[1] = 16;
      sizes[3] = size_t(n) * 16;
    }
    // Texture family: n texels (power of two) of RGBA16F / RGBA32F laid out as W x H (x D).
    const std::string texFmt = cfg.value("format", std::string("rgba32f"));
    const uint32_t texDim = cfg.value("tex_dim", 0u);
    const size_t texelBytes = texFmt == "rgba16f" ? 8 : 16;
    uint32_t log2W = 0, log2H = 0, TW = 1, TH = 1, TD = 1;
    if (family == "texture") {
      if (n & (n - 1))
        throw std::runtime_error("texture n must be a power of two");
      uint32_t ln = 0;
      while ((1u << ln) < n)
        ln++;
      // Extents are powers of two sized to the device's image limits: 2D as wide as allowed,
      // 3D with x capped at 256 (ExecuTorch-like) and the rest spread over y and z.
      const auto &L = c.props.limits;
      auto lg = [](uint32_t v) {
        uint32_t r = 0;
        while ((2u << r) <= v)
          r++;
        return r;
      };
      const uint32_t L2 = lg(L.maxImageDimension2D), L3 = lg(L.maxImageDimension3D);
      if (texDim == 3) {
        log2W = std::min({ln, 8u, L3});
        log2H = std::min(ln - log2W, L3);
      } else {
        log2W = std::min(ln, L2);
        log2H = ln - log2W;
      }
      TW = 1u << log2W;
      TH = 1u << log2H;
      TD = texDim == 3 ? (1u << (ln - log2W - log2H)) : 1u;
      if (texDim == 2 && log2H > L2)
        throw std::runtime_error("texture exceeds maxImageDimension2D");
      if (texDim == 3 && (ln - log2W - log2H) > L3)
        throw std::runtime_error("texture exceeds maxImageDimension3D");
      sizes[0] = size_t(n) * texelBytes;
      sizes[1] = 16;
      sizes[3] = threads * 16;
    }
    // Host-visible mirrors: initialization source, validation inputs and readback target.
    // Image modes read binding 2 only: binding 0 is then just the upload staging source,
    // not a storage-buffer descriptor, so maxStorageBufferRange does not apply to it.
    const bool isTex = family == "texture" && texDim != 0;
    Buf b[4];
    for (int i = 0; i < 4; i++) {
      if (sizes[i] > c.props.limits.maxStorageBufferRange && !(isTex && i == 0))
        throw std::runtime_error("maxStorageBufferRange");
      b[i] = makeBuf(c, sizes[i]);
      memset(b[i].p, 0, sizes[i]);
    }
    for (int z = 0; z < 2; z++)
      for (size_t i = 0; i < sizes[z] / 4; i++)
        ((float *)b[z].p)[i] = float((i * 13 + z * 7) % 127) * 0.0625f;
    if (family == "alu")
      for (size_t i = 0; i < threads * width; i++) {
        ((float *)b[0].p)[i] = i % 2 ? 0.25f : 0.5f;
        ((float *)b[1].p)[i] = float(i % 7 + 1) * 0.03125f;
      }
    if (family == "shared")
      for (size_t i = 0; i < sizes[0] / 4; i++)
        ((float *)b[0].p)[i] = float(i % 17);
    if (family == "dot")
      for (size_t i = 0; i < threads; i++) {
        ((uint32_t *)b[0].p)[i] = 0x01020304u + uint32_t(i % 3);
        ((uint32_t *)b[1].p)[i] = 0x01020102u;
      }
    if (family == "matrix")
      for (int z = 0; z < 2; z++) {
        if (integer)
          memset(b[z].p, 1, sizes[z]);
        else
          for (size_t i = 0; i < sizes[z] / 2; i++)
            ((uint16_t *)b[z].p)[i] = f2h(0.0625f);
      }
    if (family == "latency") {
      // Chain of nodes spaced chain_stride_bytes apart; "random" is one Sattolo cycle
      // (defeats stride prefetch), "sequential" visits nodes in address order.
      size_t step = std::max<size_t>(1, cfg.value("chain_stride_bytes", 64u) / 4),
             nodes = std::max<size_t>(1, size_t(n) / step);
      std::vector<uint32_t> order(nodes);
      std::iota(order.begin(), order.end(), 0u);
      if (cfg.value("chain_order", std::string("random")) == "random") {
        std::mt19937_64 rng(8675309);
        for (size_t i = nodes - 1; i > 0; i--) {
          std::uniform_int_distribution<size_t> d(0, i - 1);
          std::swap(order[i], order[d(rng)]);
        }
        std::vector<uint32_t> succ(nodes);
        for (size_t i = 0; i < nodes; i++)
          succ[i] = order[i];
        for (size_t i = 0; i < nodes; i++)
          ((uint32_t *)b[0].p)[i * step] = uint32_t(succ[i] * step);
      } else
        for (size_t i = 0; i < nodes; i++)
          ((uint32_t *)b[0].p)[i * step] = uint32_t(((i + 1) % nodes) * step);
    }
    if (family == "texture")
      for (size_t i = 0; i < size_t(n) * 4; i++) {
        float v = float((i / 4 * 13 + (i % 4) * 7) % 127) * 0.0625f;
        if (texelBytes == 8)
          ((uint16_t *)b[0].p)[i] = f2h(v);
        else
          ((float *)b[0].p)[i] = v;
      }
    memset(b[3].p, 0xff, sizes[3]);
    // Operand buffers the shaders actually access.
    DevBuf dv[4];
    VkBuffer use[4];
    json alloc = json::array();
    for (int i = 0; i < 4; i++) {
      if (isTex && i == 0) {
        dv[i] = makeDeviceBuf(c, 16);
        use[i] = dv[i].b;
        alloc.push_back(
            {{"binding", i}, {"bytes", 16}, {"note", "placeholder; image modes read binding 2"}});
        continue;
      }
      if (deviceLocal) {
        dv[i] = makeDeviceBuf(c, sizes[i]);
        use[i] = dv[i].b;
        copyNow(c, b[i].b, dv[i].b, sizes[i]);
        alloc.push_back({{"binding", i},
                         {"bytes", sizes[i]},
                         {"memory_type", dv[i].type},
                         {"flags", dv[i].flags},
                         {"fallback_host_visible", dv[i].fallback}});
      } else {
        use[i] = b[i].b;
        alloc.push_back(
            {{"binding", i}, {"bytes", sizes[i]}, {"memory_type", "host_coherent_mirror"}});
      }
    }
    puts(json{{"event", "allocation"},
              {"memory_mode", deviceLocal ? "device_local" : "host_coherent"},
              {"buffers", alloc}}
             .dump()
             .c_str());
    auto readback = [&]() {
      if (deviceLocal)
        copyNow(c, dv[3].b, b[3].b, sizes[3]);
    };
    // Texture family: the same texel data uploaded to an optimal-tiling image (read through
    // texelFetch), bound at binding 2 as a combined image sampler; binding 0 keeps the
    // storage-buffer copy for the buffer mode.
    Tex tex{};
    if (isTex)
      tex = makeTexture(c, b[0].b, texDim == 3 ? 3 : 2,
                        texelBytes == 8 ? VK_FORMAT_R16G16B16A16_SFLOAT
                                        : VK_FORMAT_R32G32B32A32_SFLOAT,
                        TW, TH, TD);
    VkDescriptorSetLayoutBinding binds[4];
    for (uint32_t i = 0; i < 4; i++)
      binds[i] = {i,
                  (isTex && i == 2) ? VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER
                                    : VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
                  1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
    VkDescriptorSetLayoutCreateInfo dl{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    dl.bindingCount = 4;
    dl.pBindings = binds;
    VkDescriptorSetLayout dsl;
    CHECK(vkCreateDescriptorSetLayout(c.dev, &dl, nullptr, &dsl));
    VkPushConstantRange pr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 16};
    VkPipelineLayoutCreateInfo plc{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    plc.setLayoutCount = 1;
    plc.pSetLayouts = &dsl;
    plc.pushConstantRangeCount = 1;
    plc.pPushConstantRanges = &pr;
    VkPipelineLayout pl;
    CHECK(vkCreatePipelineLayout(c.dev, &plc, nullptr, &pl));
    VkPipeline pipe = VK_NULL_HANDLE;
    VkShaderModule sm = VK_NULL_HANDLE;
    if (family != "copy") {
      std::ifstream sf(shader, std::ios::binary | std::ios::ate);
      if (!sf)
        throw std::runtime_error("shader not found");
      size_t len = sf.tellg();
      sf.seekg(0);
      std::vector<uint32_t> spv(len / 4);
      sf.read((char *)spv.data(), len);
      VkShaderModuleCreateInfo sci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
      sci.codeSize = len;
      sci.pCode = spv.data();
      CHECK(vkCreateShaderModule(c.dev, &sci, nullptr, &sm));
      uint32_t values[] = {wg, count, stride};
      VkSpecializationMapEntry entries[] = {{0, 0, 4}, {1, 4, 4}, {2, 8, 4}};
      VkSpecializationInfo spec{3, entries, 12, values};
      if (family == "latency")
        spec.mapEntryCount = 0;
      VkPipelineShaderStageRequiredSubgroupSizeCreateInfo rss{
          VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_REQUIRED_SUBGROUP_SIZE_CREATE_INFO};
      rss.requiredSubgroupSize = g_subgroup;
      VkComputePipelineCreateInfo pci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
      pci.layout = pl;
      pci.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
                   (family == "matrix" && g_sgctl) ? &rss : nullptr,
                   0,
                   VK_SHADER_STAGE_COMPUTE_BIT,
                   sm,
                   "main",
                   &spec};
      CHECK(vkCreateComputePipelines(c.dev, VK_NULL_HANDLE, 1, &pci, nullptr, &pipe));
    }
    VkDescriptorPoolSize ps[2] = {{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 4},
                                  {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1}};
    VkDescriptorPoolCreateInfo dpc{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    dpc.maxSets = 1;
    dpc.poolSizeCount = 2;
    dpc.pPoolSizes = ps;
    VkDescriptorPool dp;
    CHECK(vkCreateDescriptorPool(c.dev, &dpc, nullptr, &dp));
    VkDescriptorSetAllocateInfo da{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    da.descriptorPool = dp;
    da.descriptorSetCount = 1;
    da.pSetLayouts = &dsl;
    VkDescriptorSet ds;
    CHECK(vkAllocateDescriptorSets(c.dev, &da, &ds));
    VkDescriptorBufferInfo db[4];
    VkDescriptorImageInfo di{tex.sampler, tex.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkWriteDescriptorSet wr[4];
    for (int i = 0; i < 4; i++) {
      db[i] = {use[i], 0, (isTex && i == 0) ? 16 : sizes[i]};
      wr[i] = {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, ds,     (uint32_t)i, 0, 1,
               VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,      nullptr, &db[i], nullptr};
      if (isTex && i == 2) {
        wr[i].descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        wr[i].pImageInfo = &di;
        wr[i].pBufferInfo = nullptr;
      }
    }
    vkUpdateDescriptorSets(c.dev, 4, wr, 0, nullptr);
    VkQueryPoolCreateInfo qc{VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO};
    qc.queryType = VK_QUERY_TYPE_TIMESTAMP;
    qc.queryCount = 2;
    VkQueryPool qp;
    CHECK(vkCreateQueryPool(c.dev, &qc, nullptr, &qp));
    VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    ca.commandPool = c.pool;
    ca.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    ca.commandBufferCount = 1;
    VkCommandBuffer cb;
    CHECK(vkAllocateCommandBuffers(c.dev, &ca, &cb));
    VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence;
    CHECK(vkCreateFence(c.dev, &fc, nullptr, &fence));
    // Dispatches per timed submission; calibration raises it when a loop count is capped
    // (bounded FP16 accumulation) so every sample still reaches the target duration.
    uint32_t batch = cfg.value("batch_dispatches", 1u);
    const uint32_t pc2 = (family == "memory" && op == 0) ? cfg.value("replicas", 1u)
                         : family == "ert"               ? bits(cfg.value("alpha", 0.5f))
                         : isTex                         ? log2W
                                                         : 17u,
                   pc3 = family == "ert" ? bits(cfg.value("beta", 0.25f))
                         : isTex         ? log2H
                                         : 0u;
    auto execute = [&](uint32_t its) {
      CHECK(vkResetCommandBuffer(cb, 0));
      VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
      CHECK(vkBeginCommandBuffer(cb, &bi));
      vkCmdResetQueryPool(cb, qp, 0, 2);
      VkMemoryBarrier mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
      mb.srcAccessMask =
          VK_ACCESS_HOST_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT;
      mb.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT |
                         VK_ACCESS_TRANSFER_READ_BIT | VK_ACCESS_TRANSFER_WRITE_BIT;
      vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT,
                           VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 1, &mb, 0, nullptr, 0, nullptr);
      vkCmdWriteTimestamp(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, qp, 0);
      if (family == "copy") {
        VkBufferCopy region{0, 0, n * width * 4ull};
        vkCmdCopyBuffer(cb, use[0], use[3], 1, &region);
      } else {
        vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
        vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pl, 0, 1, &ds, 0, nullptr);
        uint32_t pc[] = {n, its, pc2, pc3};
        vkCmdPushConstants(cb, pl, VK_SHADER_STAGE_COMPUTE_BIT, 0, 16, pc);
        for (uint32_t bi = 0; bi < batch; bi++) {
          if (bi) {
            VkMemoryBarrier between{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
            between.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT;
            between.dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT;
            vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
                                 VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 1, &between, 0, nullptr,
                                 0, nullptr);
          }
          vkCmdDispatch(cb, groups, 1, 1);
        }
      }
      vkCmdWriteTimestamp(cb, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT, qp, 1);
      mb.srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT;
      mb.dstAccessMask = VK_ACCESS_HOST_READ_BIT;
      vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_HOST_BIT, 0, 1,
                           &mb, 0, nullptr, 0, nullptr);
      CHECK(vkEndCommandBuffer(cb));
      CHECK(vkResetFences(c.dev, 1, &fence));
      VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
      si.commandBufferCount = 1;
      si.pCommandBuffers = &cb;
      CHECK(vkQueueSubmit(c.q, 1, &si, fence));
      CHECK(vkWaitForFences(c.dev, 1, &fence, VK_TRUE, 10000000000ull));
      uint64_t ts[4] = {};
      CHECK(vkGetQueryPoolResults(c.dev, qp, 0, 2, sizeof(ts), ts, 16,
                                  VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT));
      if (!ts[1] || !ts[3])
        throw std::runtime_error("unavailable query");
      uint64_t mask = c.timestampBits == 64 ? UINT64_MAX : ((1ull << c.timestampBits) - 1);
      uint64_t ticks = (ts[2] - ts[0]) & mask;
      if (!ticks)
        throw std::runtime_error("zero timestamp interval");
      return double(ticks) * double(c.props.limits.timestampPeriod) * 1e-9;
    };
    auto validate = [&](uint32_t its) {
      readback();
      size_t errors = 0, checked = 0;
      double maxerr = 0;
      auto check = [&](size_t idx, double expect) {
        double got = (family == "dot") ? ((int32_t *)b[3].p)[idx]
                     : family == "latency"
                         ? ((uint32_t *)b[3].p)[idx]
                         : (family == "matrix" ? (integer ? ((int32_t *)b[3].p)[idx]
                                                          : (half ? h2f(((uint16_t *)b[3].p)[idx])
                                                                  : ((float *)b[3].p)[idx]))
                                               : ((float *)b[3].p)[idx]);
        double er = std::abs(got - expect);
        maxerr = std::max(maxerr, er);
        if (!std::isfinite(got) || er > std::max(0.005, std::abs(expect) * 0.003)) {
          if (errors < 4)
            fprintf(stderr, "CHECK idx=%zu got=%g expected=%g\n", idx, got, expect);
          errors++;
        }
        checked++;
      };
      const float *A = (float *)b[0].p;
      const float *B = (float *)b[1].p;
      if (family == "memory" || family == "copy") {
        if (op == 0 && family == "memory") {
          size_t base = threads / cfg.value("replicas", 1u);
          for (size_t id = 0; id < threads; id += std::max<size_t>(1, threads / 1024)) {
            if (id % base >= n)
              continue;
            for (uint32_t v = 0; v < width; v++) {
              double ref = 0;
              for (size_t i = id % base; i < n; i += base)
                ref += A[i * width + v];
              check(id * width + v, ref * its);
            }
          }
        } else if (op == 6 && family == "memory") {
          for (size_t g = 0; g < groups; g += std::max<size_t>(1, groups / 32))
            for (uint32_t v = 0; v < width; v++) {
              double ref = 0;
              for (size_t tid = g * wg; tid < (g + 1) * wg; tid++)
                for (size_t i = tid; i < n; i += threads)
                  ref += double(A[i * width + v]) * B[i * width + v];
              check(g * width + v, ref * its);
            }
        } else
          for (size_t i = 0; i < size_t(n) * width; i += std::max<size_t>(1, n * width / 4096)) {
            double a = A[i], bb = B[i];
            check(i, family == "copy" ? a
                     : op == 1        ? ((i / width + 17) & 127)
                     : op == 2        ? a
                     : op == 3        ? a * 2
                     : op == 4        ? a + bb
                                      : a * 2 + bb);
          }
      } else if (family == "texture") {
        // Each invocation sums texels i = id, id+threads, ... (< n) over its loops, per channel.
        for (size_t id = 0; id < threads; id += std::max<size_t>(1, threads / 512))
          for (uint32_t ch = 0; ch < 4; ch++) {
            double ref = 0;
            for (size_t i = id; i < n; i += threads)
              ref += double((i * 13 + ch * 7) % 127) * 0.0625;
            check(id * 4 + ch, ref * its);
          }
      } else if (family == "matrix") {
        for (size_t group = 0; group < groups; group += std::max<size_t>(1, groups / 16))
          for (uint32_t sg = 0; sg < subgroups; sg++)
            for (uint32_t ch = 0; ch < chains; ch++)
              for (size_t i = 0; i < M * N; i++)
                check(((group * subgroups + sg) * chains + ch) * M * N + i,
                      (integer ? double(ch) : double(ch) / 16) +
                          its * K * (integer ? 1.0 : 1.0 / 256));
      } else if (family == "alu") {
        for (size_t id = 0; id < threads; id += std::max<size_t>(1, threads / 8))
          for (uint32_t ch = 0; ch < chains; ch++)
            for (uint32_t v = 0; v < width; v++) {
              float ref = float(ch + 1) * 0.0625f + float(v) * 0.015625f;
              float alpha = A[id * width + v], beta = B[id * width + v] * float(ch + 1);
              if (half)
                beta = float((_Float16)beta);
              for (uint32_t t = 0; t < its * 16; t++) {
                ref = std::fma(ref, alpha, beta);
                if (half)
                  ref = float((_Float16)ref);
              }
              check((id * chains + ch) * width + v, ref);
            }
      } else if (family == "shared") {
        for (size_t id = 0; id < threads; id += std::max<size_t>(1, threads / 1024)) {
          uint32_t l = id % wg;
          for (uint32_t v = 0; v < width; v++) {
            double ref = 0;
            if (kind == "bw") {
              if (op == 0) {
                for (uint32_t t = 0; t < its; t++)
                  for (uint32_t k = 0; k < acc; k++)
                    ref += (((l * stride + (uint64_t(t) * acc + k) * wg) % count) * width + v) % 17;
              } else
                ref = double((uint64_t(its) * acc - 1) & 15u);
            } else if (op == 0) {
              for (uint32_t t = 0; t < its; t++)
                ref += (((l * stride + uint64_t(t) * wg) % count) * width + v) % 17;
            } else
              ref = ((((l + its) % wg) * stride) * width + v) % 17;
            check(id * width + v, ref);
          }
        }
      } else if (family == "dot") {
        for (size_t id = 0; id < threads; id += std::max<size_t>(1, threads / 128))
          for (uint32_t ch = 0; ch < chains; ch++) {
            int x = ch;
            uint32_t a0 = ((uint32_t *)b[0].p)[id], b0 = ((uint32_t *)b[1].p)[id];
            for (uint32_t t = 0; t < its; t++) {
              uint32_t a = (a0 + uint32_t(x)) & 0x07070707u;
              int step = 0;
              for (uint32_t k = 0; k < dots; k++) {
                uint32_t bb = dots > 1 ? ((b0 + k * 0x00010001u) & 0x07070707u) : b0;
                for (int v = 0; v < 4; v++)
                  step += int((a >> (v * 8)) & 255) * int((bb >> (v * 8)) & 255);
              }
              x += step;
            }
            check(id * chains + ch, x);
          }
      } else if (family == "latency") {
        const uint32_t *next = (const uint32_t *)b[0].p;
        uint32_t j = 0;
        for (uint64_t t = 0; t < uint64_t(its) * 16; t++)
          j = next[j];
        check(0, j);
      } else if (family == "ert") {
        float alpha = cfg.value("alpha", 0.5f), beta = cfg.value("beta", 0.25f);
        // Horner chain y = y*x + alpha, x = element/16 (see ert.comp).
        for (size_t i = 0; i < size_t(n) * 4; i += std::max<size_t>(1, size_t(n) * 4 / 4096)) {
          float x = A[i] * 0.0625f, y = beta;
          for (uint32_t f = 0; f < flops; f++)
            y = std::fma(y, x, alpha);
          check(i, y);
        }
      }
      return json{{"checked", checked},
                  {"errors", errors},
                  {"max_abs_error", maxerr},
                  {"pass", checked > 0 && errors == 0}};
    };
    puts(json{{"event", "schema"}, {"schema_version", 2}, {"validation_scope", "pre_and_post"}}
             .dump()
             .c_str());
    double first = execute(1);
    puts(json{{"event", "first_dispatch"},
              {"seconds", first},
              {"qualification", "after_host_initialization_not_guaranteed_cold"},
              {"config", cfg}}
             .dump()
             .c_str());
    execute(2);
    auto sanity = validate(2);
    if (!sanity["pass"].get<bool>()) {
      puts(json{{"event", "validation_failed"}, {"config", cfg}, {"validation", sanity}}
               .dump()
               .c_str());
      return 3;
    }
    // Runtime calibration preserves operation accounting; half accumulators stay bounded.
    const double target = cfg.value("target_seconds", 0.005);
    auto calibrate = [&]() {
      if (!cfg.value("calibrate", true) || family == "copy")
        return;
      const uint32_t limit = family == "shared" && half   ? 128
                             : family == "matrix" && half ? 1024u / K
                                                          : 16384;
      calibrateTiming(
          loops, batch, limit, target, cfg.value("differential", true),
          [&](uint32_t l, uint32_t b) {
            batch = b;
            return execute(l);
          },
          [&](int round, uint32_t l, uint32_t b, double sec, double fixed, uint32_t nl, uint32_t nb,
              const std::string &reason, bool stop) {
            puts(json{{"event", "calibration"},
                      {"round", round},
                      {"loops", l},
                      {"batch_dispatches", b},
                      {"seconds", sec},
                      {"fixed_fraction", fixed},
                      {"next_loops", nl},
                      {"next_batch_dispatches", nb},
                      {"reason", reason},
                      {"stop", stop}}
                     .dump()
                     .c_str());
          });
    };
    // DVFS warm-up with full-size dispatches: calibrate first, because load-based
    // governors (amdgpu, Mali) key on GPU busy %, and tiny dispatches separated by host
    // round trips never ramp the clock (Radeon 780M: 1 s of 0.08 ms dispatches left
    // samples ramping 15 -> 4.4 ms). Warm up for warmup_seconds AND until the last five
    // dispatch times agree within 3 % (cap 4 x warmup_seconds), then re-calibrate at the
    // ramped clock so samples still reach the target duration.
    // warm_up: dispatch at the calibrated size for warmup_seconds AND until the last five
    // dispatch times agree within 3 % (cap 4 x warmup_seconds); logs a warmup event.
    const double warm = cfg.value("warmup_seconds", 0.0);
    auto warm_up = [&](const char *phase) {
      if (warm <= 0)
        return;
      auto w0 = std::chrono::steady_clock::now();
      int wn = 0;
      double firstw = 0, lastw = 0;
      bool steady = false;
      std::vector<double> recent;
      auto el = [&]() {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - w0).count();
      };
      do {
        lastw = execute(loops);
        if (!wn)
          firstw = lastw;
        wn++;
        recent.push_back(lastw);
        if (recent.size() > 5)
          recent.erase(recent.begin());
        if (recent.size() == 5) {
          auto mm = std::minmax_element(recent.begin(), recent.end());
          steady = (*mm.second - *mm.first) <= 0.03 * (*mm.second);
        }
      } while (wn < 2 || el() < warm || (!steady && el() < 4 * warm));
      puts(json{{"event", "warmup"},
                {"phase", phase},
                {"dispatches", wn},
                {"first_seconds", firstw},
                {"last_seconds", lastw},
                {"steady", steady},
                {"wall_seconds", el()},
                {"batch_dispatches", batch}}
               .dump()
               .c_str());
    };
    calibrate();
    warm_up("calibration");
    calibrate();
    execute(loops);
    auto val = validate(loops);
    puts(json{{"event", "validation_pre"}, {"loops", loops}, {"validation", val}}.dump().c_str());
    if (!val["pass"].get<bool>()) {
      puts(json{
          {"event", "validation_failed"}, {"config", cfg}, {"loops", loops}, {"validation", val}}
               .dump()
               .c_str());
      return 3;
    }
    double duration = cfg.value("duration_seconds", 0.0);
    // Differential (two-point) timing: interleave loops and loops/2 so the paired
    // difference removes fixed per-dispatch cost (launch, fills, write-back).
    const bool diff =
        duration <= 0 && cfg.value("differential", true) && family != "copy" && loops >= 2;
    const uint32_t half_loops = loops / 2;
    if (diff) {
      execute(half_loops);
      auto vh = validate(half_loops);
      if (!vh["pass"].get<bool>()) {
        puts(json{{"event", "validation_failed"},
                  {"config", cfg},
                  {"loops", half_loops},
                  {"validation", vh}}
                 .dump()
                 .c_str());
        return 3;
      }
    }
    // Validation above runs on the CPU with the GPU idle (hundreds of ms for long
    // loops), long enough for the governor to drop the clock again (780M: samples
    // ramped 26 -> 7.5 ms after it). Warm up once more immediately before sampling.
    warm_up("sampling");
    auto start = std::chrono::steady_clock::now();
    int samples = cfg.value("samples", 21);
    int i = 0;
    do {
      // Leave the actual final full-length sample in the output buffer.
      const bool half_first = diff && i == samples - 1;
      auto sample_half = [&]() {
        double sh = execute(half_loops);
        puts(json{{"event", "sample_half"}, {"sample", i}, {"seconds", sh}, {"loops", half_loops}}
                 .dump()
                 .c_str());
      };
      if (half_first)
        sample_half();
      double sec = execute(loops);
      double elapsed =
          std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
      puts(json{{"event", "sample"},
                {"sample", i},
                {"seconds", sec},
                {"elapsed_seconds", elapsed},
                {"loops", loops},
                {"batch_dispatches", batch},
                {"timestamp_period_ns", c.props.limits.timestampPeriod},
                {"timestamp_valid_bits", c.timestampBits}}
               .dump()
               .c_str());
      if (diff && !half_first)
        sample_half();
      fflush(stdout);
      i++;
      if (duration > 0 && elapsed >= duration)
        break;
    } while (duration > 0 || i < samples);
    auto post = validate(loops);
    puts(json{
        {"event", "validation_post"}, {"sample", i - 1}, {"loops", loops}, {"validation", post}}
             .dump()
             .c_str());
    fflush(stdout);
    CHECK(vkDeviceWaitIdle(c.dev));
    for (auto &x : b)
      freeBuf(c, x);
    if (deviceLocal)
      for (auto &x : dv)
        freeDeviceBuf(c, x);
    vkDestroyDevice(c.dev, nullptr);
    vkDestroyInstance(c.inst, nullptr);
    return post["pass"].get<bool>() ? 0 : 3;
  } catch (const std::exception &e) {
    fprintf(stderr, "ERROR %s\n", e.what());
    return 2;
  }
}
