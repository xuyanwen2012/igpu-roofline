// Adapted from existing workspace coopmat_test.cpp; not a replacement Vulkan runtime.
static uint32_t g_subgroup = 64; static bool g_sgctl = false;

#define CHECK(x) do { VkResult r_ = (x); if (r_ != VK_SUCCESS) { fprintf(stderr, "%s failed: %d (line %d)\n", #x, (int)r_, __LINE__); exit(1); } } while (0)

// ---- f16 helpers -----------------------------------------------------------
static uint16_t f2h(float f) {
    uint32_t x; memcpy(&x, &f, 4);
    uint32_t sign = (x >> 16) & 0x8000; int32_t exp = ((x >> 23) & 0xff) - 127 + 15; uint32_t man = x & 0x7fffff;
    if (exp <= 0) return (uint16_t)sign;                       // flush tiny to zero (inputs are small ints)
    if (exp >= 31) return (uint16_t)(sign | 0x7c00);
    return (uint16_t)(sign | (exp << 10) | (man >> 13));
}
static float h2f(uint16_t h) {
    uint32_t sign = (h & 0x8000) << 16; uint32_t exp = (h >> 10) & 0x1f; uint32_t man = h & 0x3ff; uint32_t x;
    if (exp == 0) x = sign;                                    // zero/denormal -> 0
    else if (exp == 31) x = sign | 0x7f800000 | (man << 13);
    else x = sign | ((exp - 15 + 127) << 23) | (man << 13);
    float f; memcpy(&f, &x, 4); return f;
}

// ---- Vulkan context --------------------------------------------------------
struct Ctx {
    VkInstance inst{}; VkPhysicalDevice pd{}; VkDevice dev{}; VkQueue q{}; uint32_t qf = 0;
    VkCommandPool pool{}; uint32_t hostMemType = 0; VkPhysicalDeviceProperties props{}; uint32_t timestampBits=0;
};

static bool hasDeviceExt(VkPhysicalDevice pd,const char* name){
    uint32_t n=0; vkEnumerateDeviceExtensionProperties(pd,nullptr,&n,nullptr); std::vector<VkExtensionProperties> e(n);
    vkEnumerateDeviceExtensionProperties(pd,nullptr,&n,e.data()); for(auto& x:e) if(!strcmp(x.extensionName,name)) return true; return false;
}
static Ctx createCtx() {
    Ctx c;
    VkApplicationInfo ai{VK_STRUCTURE_TYPE_APPLICATION_INFO}; ai.apiVersion = VK_API_VERSION_1_3;
    VkInstanceCreateInfo ici{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO}; ici.pApplicationInfo = &ai;
    CHECK(vkCreateInstance(&ici, nullptr, &c.inst));
    uint32_t n = 1; CHECK(vkEnumeratePhysicalDevices(c.inst, &n, &c.pd));

    VkPhysicalDeviceProperties props; vkGetPhysicalDeviceProperties(c.pd, &props); c.props=props;
    fprintf(stderr,"Device: %s (Vulkan %u.%u)\n", props.deviceName, VK_VERSION_MAJOR(props.apiVersion), VK_VERSION_MINOR(props.apiVersion));

    // Cooperative matrix is optional: devices without it run every non-matrix family.
    const bool hasCm=hasDeviceExt(c.pd,"VK_KHR_cooperative_matrix"), hasPe=hasDeviceExt(c.pd,"VK_KHR_pipeline_executable_properties");
    VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR xp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR};
    VkPhysicalDeviceCooperativeMatrixFeaturesKHR cm{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
    cm.pNext=hasPe?(void*)&xp:nullptr;
    VkPhysicalDeviceVulkan13Features f13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES, hasCm?(void*)&cm:hasPe?(void*)&xp:nullptr};
    VkPhysicalDeviceVulkan12Features f12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &f13};
    VkPhysicalDeviceVulkan11Features f11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &f12};
    VkPhysicalDeviceFeatures2 f2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &f11};
    vkGetPhysicalDeviceFeatures2(c.pd, &f2);
    fprintf(stderr,"Features: cooperativeMatrix=%d shaderFloat16=%d shaderInt8=%d 16bitStorage=%d 8bitStorage=%d vulkanMemoryModel=%d subgroupSizeControl=%d\n",
           cm.cooperativeMatrix, f12.shaderFloat16, f12.shaderInt8, f11.storageBuffer16BitAccess,
           f12.storageBuffer8BitAccess, f12.vulkanMemoryModel, f13.subgroupSizeControl);
    if (!cm.cooperativeMatrix) fprintf(stderr,"Cooperative matrix not supported; matrix family disabled\n");
    VkPhysicalDeviceSubgroupProperties sgp{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SUBGROUP_PROPERTIES};
    VkPhysicalDeviceProperties2 p2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, &sgp};
    vkGetPhysicalDeviceProperties2(c.pd, &p2);
    g_subgroup = sgp.subgroupSize; g_sgctl = f13.subgroupSizeControl && f13.computeFullSubgroups;
    fprintf(stderr,"Subgroup size: %u (size control: %d)\n", g_subgroup, (int)g_sgctl);

    // Enable exactly what we use.
    VkPhysicalDeviceCooperativeMatrixFeaturesKHR eCm{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_COOPERATIVE_MATRIX_FEATURES_KHR};
    eCm.cooperativeMatrix = VK_TRUE;
    VkPhysicalDevicePipelineExecutablePropertiesFeaturesKHR ep{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_EXECUTABLE_PROPERTIES_FEATURES_KHR};ep.pipelineExecutableInfo=xp.pipelineExecutableInfo;eCm.pNext=hasPe?(void*)&ep:nullptr;
    VkPhysicalDeviceVulkan13Features e13{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES, cm.cooperativeMatrix?(void*)&eCm:hasPe?(void*)&ep:nullptr};
    e13.subgroupSizeControl = f13.subgroupSizeControl; e13.computeFullSubgroups = f13.computeFullSubgroups;
    VkPhysicalDeviceVulkan12Features e12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES, &e13};
    e13.shaderIntegerDotProduct=f13.shaderIntegerDotProduct;
    e12.shaderFloat16 = f12.shaderFloat16; e12.shaderInt8 = f12.shaderInt8;
    e12.storageBuffer8BitAccess = f12.storageBuffer8BitAccess;
    e12.vulkanMemoryModel = f12.vulkanMemoryModel; e12.vulkanMemoryModelDeviceScope = f12.vulkanMemoryModelDeviceScope;
    VkPhysicalDeviceVulkan11Features e11{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES, &e12};
    e11.storageBuffer16BitAccess = f11.storageBuffer16BitAccess;
    VkPhysicalDeviceFeatures2 e2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, &e11};

    uint32_t qn = 0; vkGetPhysicalDeviceQueueFamilyProperties(c.pd, &qn, nullptr);
    std::vector<VkQueueFamilyProperties> qp(qn); vkGetPhysicalDeviceQueueFamilyProperties(c.pd, &qn, qp.data());
    for (uint32_t i = 0; i < qn; i++) if (qp[i].queueFlags & VK_QUEUE_COMPUTE_BIT) { c.qf = i; c.timestampBits=qp[i].timestampValidBits; break; }
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qci{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO}; qci.queueFamilyIndex = c.qf; qci.queueCount = 1; qci.pQueuePriorities = &prio;
    std::vector<const char*> exts; if (cm.cooperativeMatrix) exts.push_back("VK_KHR_cooperative_matrix"); if (hasPe) exts.push_back("VK_KHR_pipeline_executable_properties");
    VkDeviceCreateInfo dci{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, &e2}; dci.queueCreateInfoCount = 1; dci.pQueueCreateInfos = &qci;
    dci.enabledExtensionCount = (uint32_t)exts.size(); dci.ppEnabledExtensionNames = exts.data();
    CHECK(vkCreateDevice(c.pd, &dci, nullptr, &c.dev));
    vkGetDeviceQueue(c.dev, c.qf, 0, &c.q);

    VkCommandPoolCreateInfo pci{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO}; pci.queueFamilyIndex = c.qf; pci.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    CHECK(vkCreateCommandPool(c.dev, &pci, nullptr, &c.pool));

    VkPhysicalDeviceMemoryProperties mp; vkGetPhysicalDeviceMemoryProperties(c.pd, &mp);
    const VkMemoryPropertyFlags want = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    for (uint32_t i = 0; i < mp.memoryTypeCount; i++) if ((mp.memoryTypes[i].propertyFlags & want) == want) { c.hostMemType = i; break; }
    return c;
}

struct Buf { VkBuffer b{}; VkDeviceMemory m{}; void* p{}; size_t size{}; };
static Buf makeBuf(Ctx& c, size_t size) {
    Buf r; r.size = size;
    VkBufferCreateInfo bci{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO}; bci.size = size; bci.usage = VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_TRANSFER_SRC_BIT | VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    CHECK(vkCreateBuffer(c.dev, &bci, nullptr, &r.b));
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(c.dev, r.b, &mr);
    VkMemoryAllocateInfo mai{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO}; mai.allocationSize = mr.size; mai.memoryTypeIndex = UINT32_MAX;
    VkPhysicalDeviceMemoryProperties mp; vkGetPhysicalDeviceMemoryProperties(c.pd,&mp);
    for(uint32_t i=0;i<mp.memoryTypeCount;i++) if((mr.memoryTypeBits&(1u<<i)) && (mp.memoryTypes[i].propertyFlags & (VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT|VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT))==(VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT|VK_MEMORY_PROPERTY_HOST_COHERENT_BIT|VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)){mai.memoryTypeIndex=i;break;}
    if(mai.memoryTypeIndex==UINT32_MAX){fprintf(stderr,"No coherent device-local host-visible allocation; staging implementation required\n");exit(2);}
    fprintf(stderr,"BUFFER bytes=%zu type=%u flags=%u\n",size,mai.memoryTypeIndex,mp.memoryTypes[mai.memoryTypeIndex].propertyFlags);
    CHECK(vkAllocateMemory(c.dev, &mai, nullptr, &r.m));
    CHECK(vkBindBufferMemory(c.dev, r.b, r.m, 0));
    CHECK(vkMapMemory(c.dev, r.m, 0, size, 0, &r.p));
    return r;
}
static void freeBuf(Ctx& c, Buf& b) { vkUnmapMemory(c.dev, b.m); vkDestroyBuffer(c.dev, b.b, nullptr); vkFreeMemory(c.dev, b.m, nullptr); }

