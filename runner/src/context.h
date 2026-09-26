// Adapted from existing workspace coopmat_test.cpp; not a replacement Vulkan runtime.
static uint32_t g_subgroup = 64;
static bool g_sgctl = false;

#define CHECK(x)                                                                                   \
  do {                                                                                             \
    VkResult r_ = (x);                                                                             \
    if (r_ != VK_SUCCESS) {                                                                        \
      fprintf(stderr, "%s failed: %d (line %d)\n", #x, (int)r_, __LINE__);                         \
      exit(1);                                                                                     \
    }                                                                                              \
  } while (0)

// ---- f16 helpers -----------------------------------------------------------
static uint16_t f2h(float f) {
  uint32_t x;
  memcpy(&x, &f, 4);
  uint32_t sign = (x >> 16) & 0x8000;
  int32_t exp = ((x >> 23) & 0xff) - 127 + 15;
  uint32_t man = x & 0x7fffff;
  if (exp <= 0)
    return (uint16_t)sign; // flush tiny to zero (inputs are small ints)
  if (exp >= 31)
    return (uint16_t)(sign | 0x7c00);
  return (uint16_t)(sign | (exp << 10) | (man >> 13));
}
static float h2f(uint16_t h) {
  uint32_t sign = (h & 0x8000) << 16;
  uint32_t exp = (h >> 10) & 0x1f;
  uint32_t man = h & 0x3ff;
  uint32_t x;
  if (exp == 0)
    x = sign; // zero/denormal -> 0
  else if (exp == 31)
    x = sign | 0x7f800000 | (man << 13);
  else
    x = sign | ((exp - 15 + 127) << 23) | (man << 13);
  float f;
  memcpy(&f, &x, 4);
  return f;
}

// ---- Vulkan context --------------------------------------------------------
struct Ctx {
  VkInstance inst{};
  VkPhysicalDevice pd{};
  VkDevice dev{};
  VkQueue q{};
  uint32_t qf = 0;
  VkCommandPool pool{};
  uint32_t hostMemType = 0;
  VkPhysicalDeviceProperties props{};
  uint32_t timestampBits = 0;
};

static bool hasDeviceExt(VkPhysicalDevice pd, const char *name) {
  uint32_t n = 0;
  vkEnumerateDeviceExtensionProperties(pd, nullptr, &n, nullptr);
  std::vector<VkExtensionProperties> e(n);
  vkEnumerateDeviceExtensionProperties(pd, nullptr, &n, e.data());
  for (auto &x : e)
    if (!strcmp(x.extensionName, name))
      return true;
  return false;
}
static std::string deviceUUID(VkPhysicalDevice pd) {
  VkPhysicalDeviceIDProperties id{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES};
  VkPhysicalDeviceProperties2 p{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &id};
  vkGetPhysicalDeviceProperties2(pd, &p);
  std::string result;
  for (auto b : id.deviceUUID) {
    char hex[3];
    snprintf(hex, sizeof(hex), "%02x", b);
    result += hex;
  }
  return result;
}
// Pick the GPU to measure. Hosts often expose a CPU rasterizer (llvmpipe) next to the
// GPU, so CPU devices are skipped; IGPU_ROOFLINE_GPU selects by name substring.
static VkPhysicalDevice pickPhysicalDevice(VkInstance inst) {
  uint32_t n = 0;
  CHECK(vkEnumeratePhysicalDevices(inst, &n, nullptr));
  std::vector<VkPhysicalDevice> all(n);
  CHECK(vkEnumeratePhysicalDevices(inst, &n, all.data()));
  const char *want = getenv("IGPU_ROOFLINE_GPU");
  const char *uuid = getenv("IGPU_ROOFLINE_UUID");
  VkPhysicalDevice pick = VK_NULL_HANDLE;
  for (auto pd : all) {
    VkPhysicalDeviceProperties p;
    vkGetPhysicalDeviceProperties(pd, &p);
    if (uuid && *uuid) {
      if (deviceUUID(pd) == uuid) {
        pick = pd;
        break;
      }
      continue;
    }
    if (want && *want) {
      if (strstr(p.deviceName, want)) {
        pick = pd;
        break;
      }
      continue;
    }
    if (p.deviceType != VK_PHYSICAL_DEVICE_TYPE_CPU) {
      pick = pd;
      break;
    }
  }
  if (!pick)
    throw std::runtime_error(want && *want ? "no Vulkan device matches IGPU_ROOFLINE_GPU"
                                           : "no non-CPU Vulkan device");
  return pick;
}
static Ctx createCtx(bool identityOnly = false) {
  Ctx c;
  VkApplicationInfo ai{VK_STRUCTURE_TYPE_APPLICATION_INFO};
  ai.apiVersion = VK_API_VERSION_1_3;
  VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
  ici.pApplicationInfo = &ai;
  CHECK(vkCreateInstance(&ici, nullptr, &c.inst));
  c.pd = pickPhysicalDevice(c.inst);

  VkPhysicalDeviceProperties props;
  vkGetPhysicalDeviceProperties(c.pd, &props);
  c.props = props;
  if (identityOnly)
    return c;
  fprintf(stderr, "Device: %s (Vulkan %u.%u)\n", props.deviceName,
          VK_VERSION_MAJOR(props.apiVersion), VK_VERSION_MINOR(props.apiVersion));

  // Cooperative matrix is optional: devices without it run every non-matrix family.
  const bool hasCm = hasDeviceExt(c.pd, "VK_KHR_cooperative_matrix");
  VkPhysicalDeviceCooperativeMatrixFeaturesKHR cm{
      VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
  VkPhysicalDeviceVulkan13Features f13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
                                       hasCm ? (void *)&cm : nullptr};
  VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &f13};
  VkPhysicalDeviceVulkan11Features f11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &f12};
  VkPhysicalDeviceFeatures2 f2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &f11};
  vkGetPhysicalDeviceFeatures2(c.pd, &f2);
  fprintf(stderr,
          "Features: cooperativeMatrix=%d shaderFloat16=%d shaderInt8=%d 16bitStorage=%d "
          "8bitStorage=%d vulkanMemoryModel=%d subgroupSizeControl=%d\n",
          cm.cooperativeMatrix, f12.shaderFloat16, f12.shaderInt8, f11.storageBuffer16BitAccess,
          f12.storageBuffer8BitAccess, f12.vulkanMemoryModel, f13.subgroupSizeControl);
  if (!cm.cooperativeMatrix)
    fprintf(stderr, "Cooperative matrix not supported; matrix family disabled\n");
  VkPhysicalDeviceSubgroupProperties sgp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
  VkPhysicalDeviceProperties2 p2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &sgp};
  vkGetPhysicalDeviceProperties2(c.pd, &p2);
  g_subgroup = sgp.subgroupSize;
  g_sgctl = f13.subgroupSizeControl && f13.computeFullSubgroups;
  fprintf(stderr, "Subgroup size: %u (size control: %d)\n", g_subgroup, (int)g_sgctl);

  // Enable exactly what we use.
  VkPhysicalDeviceCooperativeMatrixFeaturesKHR eCm{
      VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
  eCm.cooperativeMatrix = VK_TRUE;
  VkPhysicalDeviceVulkan13Features e13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
                                       cm.cooperativeMatrix ? (void *)&eCm : nullptr};
  e13.subgroupSizeControl = f13.subgroupSizeControl;
  e13.computeFullSubgroups = f13.computeFullSubgroups;
  VkPhysicalDeviceVulkan12Features e12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &e13};
  e13.shaderIntegerDotProduct = f13.shaderIntegerDotProduct;
  e12.shaderFloat16 = f12.shaderFloat16;
  e12.shaderInt8 = f12.shaderInt8;
  e12.storageBuffer8BitAccess = f12.storageBuffer8BitAccess;
  e12.vulkanMemoryModel = f12.vulkanMemoryModel;
  e12.vulkanMemoryModelDeviceScope = f12.vulkanMemoryModelDeviceScope;
  VkPhysicalDeviceVulkan11Features e11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &e12};
  e11.storageBuffer16BitAccess = f11.storageBuffer16BitAccess;
  VkPhysicalDeviceFeatures2 e2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &e11};

  uint32_t qn = 0;
  vkGetPhysicalDeviceQueueFamilyProperties(c.pd, &qn, nullptr);
  std::vector<VkQueueFamilyProperties> qp(qn);
  vkGetPhysicalDeviceQueueFamilyProperties(c.pd, &qn, qp.data());
  for (uint32_t i = 0; i < qn; i++)
    if (qp[i].queueFlags & VK_QUEUE_COMPUTE_BIT) {
      c.qf = i;
      c.timestampBits = qp[i].timestampValidBits;
      break;
    }
  float prio = 1.0f;
  VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
  qci.queueFamilyIndex = c.qf;
  qci.queueCount = 1;
  qci.pQueuePriorities = &prio;
  std::vector<const char *> exts;
  if (cm.cooperativeMatrix)
    exts.push_back("VK_KHR_cooperative_matrix");
  VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, &e2};
  dci.queueCreateInfoCount = 1;
  dci.pQueueCreateInfos = &qci;
  dci.enabledExtensionCount = (uint32_t)exts.size();
  dci.ppEnabledExtensionNames = exts.data();
  CHECK(vkCreateDevice(c.pd, &dci, nullptr, &c.dev));
  vkGetDeviceQueue(c.dev, c.qf, 0, &c.q);

  VkCommandPoolCreateInfo pci{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
  pci.queueFamilyIndex = c.qf;
  pci.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
  CHECK(vkCreateCommandPool(c.dev, &pci, nullptr, &c.pool));

  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
  const VkMemoryPropertyFlags want =
      VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
  for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
    if ((mp.memoryTypes[i].propertyFlags & want) == want) {
      c.hostMemType = i;
      break;
    }
  return c;
}

struct Buf {
  VkBuffer b{};
  VkDeviceMemory m{};
  void *p{};
  size_t size{};
};
static Buf makeBuf(Ctx &c, size_t size) {
  Buf r;
  r.size = size;
  VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
  bci.size = size;
  bci.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
              VK_BUFFER_USAGE_TRANSFER_DST_BIT;
  CHECK(vkCreateBuffer(c.dev, &bci, nullptr, &r.b));
  VkMemoryRequirements mr;
  vkGetBufferMemoryRequirements(c.dev, r.b, &mr);
  VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
  mai.allocationSize = mr.size;
  mai.memoryTypeIndex = UINT32_MAX;
  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
  for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
    if ((mr.memoryTypeBits & (1u << i)) &&
        (mp.memoryTypes[i].propertyFlags &
         (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT |
          VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) ==
            (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT |
             VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) {
      mai.memoryTypeIndex = i;
      break;
    }
  if (mai.memoryTypeIndex == UINT32_MAX) {
    fprintf(stderr,
            "No coherent device-local host-visible allocation; staging implementation required\n");
    exit(2);
  }
  fprintf(stderr, "BUFFER bytes=%zu type=%u flags=%u\n", size, mai.memoryTypeIndex,
          mp.memoryTypes[mai.memoryTypeIndex].propertyFlags);
  CHECK(vkAllocateMemory(c.dev, &mai, nullptr, &r.m));
  CHECK(vkBindBufferMemory(c.dev, r.b, r.m, 0));
  CHECK(vkMapMemory(c.dev, r.m, 0, size, 0, &r.p));
  return r;
}
static void freeBuf(Ctx &c, Buf &b) {
  if (b.p)
    vkUnmapMemory(c.dev, b.m);
  vkDestroyBuffer(c.dev, b.b, nullptr);
  vkFreeMemory(c.dev, b.m, nullptr);
}

// v2: GPU-only data buffer. Textbook bandwidth measurement keeps operands in
// DEVICE_LOCAL memory that is not host-visible (no host caching/IO-coherency
// attributes); data moves through host-visible staging copies outside timing.
// Falls back to a host-visible type only if the driver offers no such type.
struct DevBuf {
  VkBuffer b{};
  VkDeviceMemory m{};
  uint32_t type = 0;
  uint32_t flags = 0;
  bool fallback = false;
};
static DevBuf makeDeviceBuf(Ctx &c, size_t size) {
  DevBuf r;
  VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
  bci.size = size;
  bci.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT |
              VK_BUFFER_USAGE_TRANSFER_DST_BIT;
  CHECK(vkCreateBuffer(c.dev, &bci, nullptr, &r.b));
  VkMemoryRequirements mr;
  vkGetBufferMemoryRequirements(c.dev, r.b, &mr);
  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
  uint32_t pick = UINT32_MAX;
  // Prefer exactly DEVICE_LOCAL (no host-visible, lazily-allocated or protected bits).
  for (uint32_t i = 0; i < mp.memoryTypeCount && pick == UINT32_MAX; i++)
    if ((mr.memoryTypeBits & (1u << i)) &&
        mp.memoryTypes[i].propertyFlags == VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)
      pick = i;
  for (uint32_t i = 0; i < mp.memoryTypeCount && pick == UINT32_MAX; i++)
    if ((mr.memoryTypeBits & (1u << i)) &&
        (mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) &&
        !(mp.memoryTypes[i].propertyFlags &
          (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT |
           VK_MEMORY_PROPERTY_PROTECTED_BIT)))
      pick = i;
  if (pick == UINT32_MAX) {
    for (uint32_t i = 0; i < mp.memoryTypeCount && pick == UINT32_MAX; i++)
      if ((mr.memoryTypeBits & (1u << i)) &&
          (mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT) &&
          !(mp.memoryTypes[i].propertyFlags &
            (VK_MEMORY_PROPERTY_LAZILY_ALLOCATED_BIT | VK_MEMORY_PROPERTY_PROTECTED_BIT)))
        pick = i;
    r.fallback = true;
  }
  if (pick == UINT32_MAX) {
    fprintf(stderr, "No device-local memory type for buffer\n");
    exit(2);
  }
  r.type = pick;
  r.flags = mp.memoryTypes[pick].propertyFlags;
  VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
  mai.allocationSize = mr.size;
  mai.memoryTypeIndex = pick;
  CHECK(vkAllocateMemory(c.dev, &mai, nullptr, &r.m));
  CHECK(vkBindBufferMemory(c.dev, r.b, r.m, 0));
  fprintf(stderr, "DEVICE BUFFER bytes=%zu type=%u flags=%u fallback=%d\n", size, r.type, r.flags,
          (int)r.fallback);
  return r;
}
static void freeDeviceBuf(Ctx &c, DevBuf &b) {
  vkDestroyBuffer(c.dev, b.b, nullptr);
  vkFreeMemory(c.dev, b.m, nullptr);
}

// Sampled image for the texture family: device-local, optimal tiling, uploaded from a
// staging buffer and left in SHADER_READ_ONLY_OPTIMAL; nearest sampler (texelFetch
// ignores filtering but a combined image sampler needs one).
struct Tex {
  VkImage img{};
  VkDeviceMemory mem{};
  VkImageView view{};
  VkSampler sampler{};
};
static Tex makeTexture(Ctx &c, VkBuffer staging, int dim, VkFormat fmt, uint32_t w, uint32_t h,
                       uint32_t d) {
  Tex t;
  VkImageCreateInfo ici{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
  ici.imageType = dim == 3 ? VK_IMAGE_TYPE_3D : VK_IMAGE_TYPE_2D;
  ici.format = fmt;
  ici.extent = {w, h, dim == 3 ? d : 1u};
  ici.mipLevels = 1;
  ici.arrayLayers = 1;
  ici.samples = VK_SAMPLE_COUNT_1_BIT;
  ici.tiling = VK_IMAGE_TILING_OPTIMAL;
  ici.usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT;
  ici.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  CHECK(vkCreateImage(c.dev, &ici, nullptr, &t.img));
  VkMemoryRequirements mr;
  vkGetImageMemoryRequirements(c.dev, t.img, &mr);
  VkPhysicalDeviceMemoryProperties mp;
  vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
  uint32_t pick = UINT32_MAX;
  for (uint32_t i = 0; i < mp.memoryTypeCount && pick == UINT32_MAX; i++)
    if ((mr.memoryTypeBits & (1u << i)) &&
        (mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT))
      pick = i;
  if (pick == UINT32_MAX) {
    fprintf(stderr, "No device-local memory type for image\n");
    exit(2);
  }
  VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
  mai.allocationSize = mr.size;
  mai.memoryTypeIndex = pick;
  CHECK(vkAllocateMemory(c.dev, &mai, nullptr, &t.mem));
  CHECK(vkBindImageMemory(c.dev, t.img, t.mem, 0));
  fprintf(stderr, "IMAGE %dD %ux%ux%u format=%d bytes=%llu type=%u\n", dim, w, h, d, (int)fmt,
          (unsigned long long)mr.size, pick);
  VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
  ca.commandPool = c.pool;
  ca.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
  ca.commandBufferCount = 1;
  VkCommandBuffer cb;
  CHECK(vkAllocateCommandBuffers(c.dev, &ca, &cb));
  VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
  bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
  CHECK(vkBeginCommandBuffer(cb, &bi));
  VkImageMemoryBarrier ib{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
  ib.srcQueueFamilyIndex = ib.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
  ib.image = t.img;
  ib.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  ib.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED;
  ib.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  ib.srcAccessMask = 0;
  ib.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT | VK_PIPELINE_STAGE_HOST_BIT,
                       VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 0, nullptr, 0, nullptr, 1, &ib);
  VkBufferImageCopy region{};
  region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
  region.imageExtent = ici.extent;
  vkCmdCopyBufferToImage(cb, staging, t.img, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
  ib.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
  ib.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
  ib.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  ib.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
  vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0,
                       0, nullptr, 0, nullptr, 1, &ib);
  CHECK(vkEndCommandBuffer(cb));
  VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
  VkFence f;
  CHECK(vkCreateFence(c.dev, &fc, nullptr, &f));
  VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
  si.commandBufferCount = 1;
  si.pCommandBuffers = &cb;
  CHECK(vkQueueSubmit(c.q, 1, &si, f));
  CHECK(vkWaitForFences(c.dev, 1, &f, VK_TRUE, 60000000000ull));
  vkDestroyFence(c.dev, f, nullptr);
  vkFreeCommandBuffers(c.dev, c.pool, 1, &cb);
  VkImageViewCreateInfo vci{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
  vci.image = t.img;
  vci.viewType = dim == 3 ? VK_IMAGE_VIEW_TYPE_3D : VK_IMAGE_VIEW_TYPE_2D;
  vci.format = fmt;
  vci.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
  CHECK(vkCreateImageView(c.dev, &vci, nullptr, &t.view));
  VkSamplerCreateInfo sci{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
  sci.magFilter = sci.minFilter = VK_FILTER_NEAREST;
  sci.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
  sci.addressModeU = sci.addressModeV = sci.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
  CHECK(vkCreateSampler(c.dev, &sci, nullptr, &t.sampler));
  return t;
}
// One-shot buffer copy with full barriers, used only outside timed regions.
static void copyNow(Ctx &c, VkBuffer src, VkBuffer dst, size_t size) {
  VkCommandBufferAllocateInfo ca{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
  ca.commandPool = c.pool;
  ca.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
  ca.commandBufferCount = 1;
  VkCommandBuffer cb;
  CHECK(vkAllocateCommandBuffers(c.dev, &ca, &cb));
  VkCommandBufferBeginInfo bi{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
  bi.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
  CHECK(vkBeginCommandBuffer(cb, &bi));
  VkMemoryBarrier mb{VK_STRUCTURE_TYPE_MEMORY_BARRIER};
  mb.srcAccessMask =
      VK_ACCESS_HOST_WRITE_BIT | VK_ACCESS_SHADER_WRITE_BIT | VK_ACCESS_TRANSFER_WRITE_BIT;
  mb.dstAccessMask = VK_ACCESS_TRANSFER_READ_BIT | VK_ACCESS_TRANSFER_WRITE_BIT;
  vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT | VK_PIPELINE_STAGE_HOST_BIT,
                       VK_PIPELINE_STAGE_TRANSFER_BIT, 0, 1, &mb, 0, nullptr, 0, nullptr);
  VkBufferCopy region{0, 0, size};
  vkCmdCopyBuffer(cb, src, dst, 1, &region);
  mb.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
  mb.dstAccessMask =
      VK_ACCESS_HOST_READ_BIT | VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT;
  vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_TRANSFER_BIT,
                       VK_PIPELINE_STAGE_HOST_BIT | VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 1, &mb,
                       0, nullptr, 0, nullptr);
  CHECK(vkEndCommandBuffer(cb));
  VkFenceCreateInfo fc{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
  VkFence f;
  CHECK(vkCreateFence(c.dev, &fc, nullptr, &f));
  VkSubmitInfo si{VK_STRUCTURE_TYPE_SUBMIT_INFO};
  si.commandBufferCount = 1;
  si.pCommandBuffers = &cb;
  CHECK(vkQueueSubmit(c.q, 1, &si, f));
  CHECK(vkWaitForFences(c.dev, 1, &f, VK_TRUE, 60000000000ull));
  vkDestroyFence(c.dev, f, nullptr);
  vkFreeCommandBuffers(c.dev, c.pool, 1, &cb);
}
