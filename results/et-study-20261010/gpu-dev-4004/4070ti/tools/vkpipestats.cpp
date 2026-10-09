// vkpipestats: create a compute pipeline from SPIR-V and print the driver's
// VK_KHR_pipeline_executable_properties statistics (registers, shared memory,
// spills, ...). Compiles the pipeline only; never dispatches.
//
// usage: vkpipestats <shader.spv> <lx> <ly> <lz> [spec_id=value ...]
//   env VKPS_DEVICE=<substring>   pick the physical device by name (default: first discrete)
//   env VKPS_IR=1                 also print internal representations (if any)
// Descriptor bindings and push constants are reflected from the SPIR-V.
#include <dlfcn.h>
#include <vulkan/vulkan.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <string>
#include <vector>

#define CHECK(x)                                                        \
  do {                                                                  \
    VkResult r_ = (x);                                                  \
    if (r_ != VK_SUCCESS) {                                             \
      fprintf(stderr, "%s failed: %d (line %d)\n", #x, r_, __LINE__);   \
      exit(1);                                                          \
    }                                                                   \
  } while (0)

static PFN_vkGetInstanceProcAddr gipa;
#define IFN(inst, name) auto name = (PFN_##name)gipa(inst, #name)

struct Reflect {
  std::map<uint32_t, VkDescriptorType> bindings;  // set 0 only
  bool push = false;
};

static Reflect reflect(const std::vector<uint32_t>& w) {
  Reflect out;
  std::map<uint32_t, uint32_t> binding, set;
  std::map<uint32_t, bool> block, bufferblock;
  std::map<uint32_t, std::vector<uint32_t>> types;  // id -> instruction words
  struct Var { uint32_t id, ptr, sc; };
  std::vector<Var> vars;
  for (size_t i = 5; i < w.size();) {
    uint32_t op = w[i] & 0xffff, n = w[i] >> 16;
    if (n == 0) break;
    const uint32_t* a = &w[i];
    if (op == 71) {  // OpDecorate
      if (a[2] == 33) binding[a[1]] = a[3];
      if (a[2] == 34) set[a[1]] = a[3];
      if (a[2] == 2) block[a[1]] = true;
      if (a[2] == 3) bufferblock[a[1]] = true;
    } else if (op == 59) {  // OpVariable
      vars.push_back({a[2], a[1], a[3]});
    } else if (op >= 19 && op <= 39) {  // type declarations
      types[a[1]] = std::vector<uint32_t>(a, a + n);
    }
    i += n;
  }
  auto strip = [&](uint32_t t) {
    // unwrap arrays / runtime arrays
    while (types.count(t) && ((types[t][0] & 0xffff) == 28 || (types[t][0] & 0xffff) == 29))
      t = types[t][2];
    return t;
  };
  for (auto& v : vars) {
    if (v.sc == 9) { out.push = true; continue; }
    if (!binding.count(v.id)) continue;
    if (set.count(v.id) && set[v.id] != 0) continue;
    uint32_t pointee = strip(types[v.ptr][3]);
    uint32_t op = types[pointee][0] & 0xffff;
    VkDescriptorType dt;
    if (v.sc == 12) dt = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
    else if (v.sc == 2) dt = bufferblock[pointee] ? VK_DESCRIPTOR_TYPE_STORAGE_BUFFER : VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER;
    else if (op == 27) dt = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
    else if (op == 25) {
      uint32_t sampled = types[pointee][7], dim = types[pointee][3];
      if (dim == 5) dt = sampled == 2 ? VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER : VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER;
      else dt = sampled == 2 ? VK_DESCRIPTOR_TYPE_STORAGE_IMAGE : VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE;
    } else if (op == 26) dt = VK_DESCRIPTOR_TYPE_SAMPLER;
    else { fprintf(stderr, "unknown binding type op %u\n", op); exit(1); }
    out.bindings[binding[v.id]] = dt;
  }
  return out;
}

int main(int argc, char** argv) {
  if (argc < 5) { fprintf(stderr, "usage: %s shader.spv lx ly lz [id=val ...]\n", argv[0]); return 2; }
  std::ifstream f(argv[1], std::ios::binary | std::ios::ate);
  if (!f) { perror(argv[1]); return 1; }
  std::vector<uint32_t> code(f.tellg() / 4);
  f.seekg(0);
  f.read((char*)code.data(), code.size() * 4);

  void* lib = dlopen("libvulkan.so.1", RTLD_NOW);
  if (!lib) { fprintf(stderr, "no libvulkan.so.1\n"); return 1; }
  gipa = (PFN_vkGetInstanceProcAddr)dlsym(lib, "vkGetInstanceProcAddr");
  IFN(nullptr, vkCreateInstance);
  VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
  app.apiVersion = VK_API_VERSION_1_3;
  VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  ici.pApplicationInfo = &app;
  VkInstance inst;
  CHECK(vkCreateInstance(&ici, nullptr, &inst));
  IFN(inst, vkEnumeratePhysicalDevices);
  IFN(inst, vkGetPhysicalDeviceProperties);
  IFN(inst, vkGetPhysicalDeviceFeatures2);
  IFN(inst, vkEnumerateDeviceExtensionProperties);
  IFN(inst, vkGetPhysicalDeviceQueueFamilyProperties);
  IFN(inst, vkCreateDevice);
  IFN(inst, vkGetDeviceProcAddr);

  uint32_t n = 0;
  vkEnumeratePhysicalDevices(inst, &n, nullptr);
  std::vector<VkPhysicalDevice> pds(n);
  vkEnumeratePhysicalDevices(inst, &n, pds.data());
  const char* want = getenv("VKPS_DEVICE");
  VkPhysicalDevice pd = VK_NULL_HANDLE;
  VkPhysicalDeviceProperties props;
  for (auto p : pds) {
    vkGetPhysicalDeviceProperties(p, &props);
    if (want ? strstr(props.deviceName, want) != nullptr
             : props.deviceType == VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) { pd = p; break; }
  }
  if (!pd) { fprintf(stderr, "device not found\n"); return 1; }
  vkGetPhysicalDeviceProperties(pd, &props);
  fprintf(stderr, "device: %s driver 0x%x\n", props.deviceName, props.driverVersion);

  // Enable every supported feature from the chains we know about.
  VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR pe{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR};
  VkPhysicalDeviceCooperativeMatrixFeaturesKHR cm{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR, &pe};
  VkPhysicalDeviceShaderClockFeaturesKHR clk{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_CLOCK_FEATURES_KHR, &cm};
  VkPhysicalDeviceVulkan13Features v13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES, &clk};
  VkPhysicalDeviceVulkan12Features v12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &v13};
  VkPhysicalDeviceVulkan11Features v11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &v12};
  VkPhysicalDeviceFeatures2 feats{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &v11};
  vkGetPhysicalDeviceFeatures2(pd, &feats);
  cm.cooperativeMatrixRobustBufferAccess = VK_FALSE;
  feats.features.robustBufferAccess = VK_FALSE;  // match a normal app
  v13.robustImageAccess = VK_FALSE;
  if (!pe.pipelineExecutableInfo) { fprintf(stderr, "pipelineExecutableInfo unsupported\n"); return 1; }

  vkEnumerateDeviceExtensionProperties(pd, nullptr, &n, nullptr);
  std::vector<VkExtensionProperties> exts(n);
  vkEnumerateDeviceExtensionProperties(pd, nullptr, &n, exts.data());
  std::vector<const char*> en;
  for (const char* e : {VK_KHR_PIPELINE_EXECUTABLE_PROPERTIES_EXTENSION_NAME, VK_KHR_COOPERATIVE_MATRIX_EXTENSION_NAME,
                        VK_KHR_SHADER_CLOCK_EXTENSION_NAME, "VK_KHR_workgroup_memory_explicit_layout"})
    for (auto& x : exts) if (!strcmp(x.extensionName, e)) en.push_back(e);

  vkGetPhysicalDeviceQueueFamilyProperties(pd, &n, nullptr);
  std::vector<VkQueueFamilyProperties> qf(n);
  vkGetPhysicalDeviceQueueFamilyProperties(pd, &n, qf.data());
  uint32_t qfi = 0;
  for (uint32_t i = 0; i < n; ++i) if (qf[i].queueFlags & VK_QUEUE_COMPUTE_BIT) { qfi = i; break; }
  float prio = 1.f;
  VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
  qci.queueFamilyIndex = qfi; qci.queueCount = 1; qci.pQueuePriorities = &prio;
  VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, &feats};
  dci.queueCreateInfoCount = 1; dci.pQueueCreateInfos = &qci;
  dci.enabledExtensionCount = en.size(); dci.ppEnabledExtensionNames = en.data();
  VkDevice dev;
  CHECK(vkCreateDevice(pd, &dci, nullptr, &dev));
#define DFN(name) auto name = (PFN_##name)vkGetDeviceProcAddr(dev, #name)
  DFN(vkCreateShaderModule); DFN(vkCreateDescriptorSetLayout); DFN(vkCreatePipelineLayout);
  DFN(vkCreateComputePipelines); DFN(vkGetPipelineExecutablePropertiesKHR);
  DFN(vkGetPipelineExecutableStatisticsKHR); DFN(vkGetPipelineExecutableInternalRepresentationsKHR);
  DFN(vkDestroyDevice); DFN(vkCreatePipelineCache); DFN(vkGetPipelineCacheData);

  Reflect rf = reflect(code);
  std::vector<VkDescriptorSetLayoutBinding> lb;
  for (auto& [b, t] : rf.bindings) lb.push_back({b, t, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr});
  VkDescriptorSetLayoutCreateInfo dl{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
  dl.bindingCount = lb.size(); dl.pBindings = lb.data();
  VkDescriptorSetLayout dsl;
  CHECK(vkCreateDescriptorSetLayout(dev, &dl, nullptr, &dsl));
  VkPushConstantRange pcr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 128};
  VkPipelineLayoutCreateInfo pl{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
  pl.setLayoutCount = 1; pl.pSetLayouts = &dsl;
  pl.pushConstantRangeCount = rf.push ? 1 : 0; pl.pPushConstantRanges = &pcr;
  VkPipelineLayout layout;
  CHECK(vkCreatePipelineLayout(dev, &pl, nullptr, &layout));

  VkShaderModuleCreateInfo smi{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
  smi.codeSize = code.size() * 4; smi.pCode = code.data();
  VkShaderModule sm;
  CHECK(vkCreateShaderModule(dev, &smi, nullptr, &sm));

  std::vector<VkSpecializationMapEntry> me;
  std::vector<int32_t> vals;
  for (int i = 0; i < 3; ++i) vals.push_back(atoi(argv[2 + i]));
  for (int i = 0; i < 3; ++i) me.push_back({(uint32_t)i, (uint32_t)(i * 4), 4});
  for (int i = 5; i < argc; ++i) {
    int id, v;
    if (sscanf(argv[i], "%d=%d", &id, &v) != 2) { fprintf(stderr, "bad spec %s\n", argv[i]); return 2; }
    me.push_back({(uint32_t)id, (uint32_t)(vals.size() * 4), 4});
    vals.push_back(v);
  }
  VkSpecializationInfo si{(uint32_t)me.size(), me.data(), vals.size() * 4, vals.data()};
  VkComputePipelineCreateInfo cpi{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
  cpi.flags = VK_PIPELINE_CREATE_CAPTURE_STATISTICS_BIT_KHR | VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR;
  cpi.stage = {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, nullptr, 0, VK_SHADER_STAGE_COMPUTE_BIT, sm, "main", &si};
  cpi.layout = layout;
  VkPipelineCache cache = VK_NULL_HANDLE;
  VkPipelineCacheCreateInfo pcci{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
  CHECK(vkCreatePipelineCache(dev, &pcci, nullptr, &cache));
  VkPipeline pipe;
  CHECK(vkCreateComputePipelines(dev, cache, 1, &cpi, nullptr, &pipe));
  if (const char* cp = getenv("VKPS_CACHE")) {  // dump the pipeline cache blob
    size_t sz = 0;
    vkGetPipelineCacheData(dev, cache, &sz, nullptr);
    std::vector<char> blob(sz);
    vkGetPipelineCacheData(dev, cache, &sz, blob.data());
    std::ofstream(cp, std::ios::binary).write(blob.data(), sz);
    fprintf(stderr, "cache: %zu bytes -> %s\n", sz, cp);
  }

  VkPipelineInfoKHR pi{VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR, nullptr, pipe};
  vkGetPipelineExecutablePropertiesKHR(dev, &pi, &n, nullptr);
  std::vector<VkPipelineExecutablePropertiesKHR> ep(n, {VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_PROPERTIES_KHR});
  vkGetPipelineExecutablePropertiesKHR(dev, &pi, &n, ep.data());
  for (uint32_t e = 0; e < ep.size(); ++e) {
    printf("executable %u: %s (%s) subgroup %u\n", e, ep[e].name, ep[e].description, ep[e].subgroupSize);
    VkPipelineExecutableInfoKHR ei{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INFO_KHR, nullptr, pipe, e};
    uint32_t sn = 0;
    vkGetPipelineExecutableStatisticsKHR(dev, &ei, &sn, nullptr);
    std::vector<VkPipelineExecutableStatisticKHR> st(sn, {VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_STATISTIC_KHR});
    vkGetPipelineExecutableStatisticsKHR(dev, &ei, &sn, st.data());
    for (auto& s : st) {
      printf("  %-40s ", s.name);
      switch (s.format) {
        case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_BOOL32_KHR: printf("%s", s.value.b32 ? "true" : "false"); break;
        case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_INT64_KHR: printf("%lld", (long long)s.value.i64); break;
        case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_UINT64_KHR: printf("%llu", (unsigned long long)s.value.u64); break;
        case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_FLOAT64_KHR: printf("%g", s.value.f64); break;
        default: break;
      }
      printf("   # %s\n", s.description);
    }
    if (getenv("VKPS_IR")) {
      uint32_t rn = 0;
      vkGetPipelineExecutableInternalRepresentationsKHR(dev, &ei, &rn, nullptr);
      std::vector<VkPipelineExecutableInternalRepresentationKHR> ir(rn, {VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INTERNAL_REPRESENTATION_KHR});
      vkGetPipelineExecutableInternalRepresentationsKHR(dev, &ei, &rn, ir.data());
      std::vector<std::vector<char>> buf(rn);
      for (uint32_t r = 0; r < rn; ++r) { buf[r].resize(ir[r].dataSize); ir[r].pData = buf[r].data(); }
      vkGetPipelineExecutableInternalRepresentationsKHR(dev, &ei, &rn, ir.data());
      for (uint32_t r = 0; r < rn; ++r)
        printf("  --- IR %s (%s), %zu bytes%s\n%.*s\n", ir[r].name, ir[r].description, ir[r].dataSize,
               ir[r].isText ? "" : " binary", ir[r].isText ? (int)ir[r].dataSize : 0, buf[r].data());
    }
  }
  vkDestroyDevice(dev, nullptr);
  return 0;
}
