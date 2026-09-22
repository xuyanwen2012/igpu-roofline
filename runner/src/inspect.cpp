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
#include "nlohmann/json.hpp"
#include "inspection_context.h"
using json=nlohmann::json;
static json caps(Ctx& c){
 json j={{"gpu",c.props.deviceName},{"api_version",c.props.apiVersion},{"driver_version",c.props.driverVersion},{"timestamp_period_ns",c.props.limits.timestampPeriod},{"timestamp_valid_bits",c.timestampBits},{"subgroup",g_subgroup},{"max_shared_bytes",c.props.limits.maxComputeSharedMemorySize},{"max_workgroup_invocations",c.props.limits.maxComputeWorkGroupInvocations},{"max_storage_buffer_range",c.props.limits.maxStorageBufferRange}};
 uint32_t n=0; CHECK(vkEnumerateDeviceExtensionProperties(c.pd,nullptr,&n,nullptr));std::vector<VkExtensionProperties> e(n);CHECK(vkEnumerateDeviceExtensionProperties(c.pd,nullptr,&n,e.data()));j["extensions"]=json::array();for(auto& x:e)j["extensions"].push_back(x.extensionName);
 auto fn=(PFN_vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR)vkGetInstanceProcAddr(c.inst,"vkGetPhysicalDeviceCooperativeMatrixPropertiesKHR");
 bool hasCmExt=false;for(auto& x:e)if(!strcmp(x.extensionName,"VK_KHR_cooperative_matrix"))hasCmExt=true;
 j["matrix_shapes"]=json::array();
 if(fn&&hasCmExt){CHECK(fn(c.pd,&n,nullptr));std::vector<VkCooperativeMatrixPropertiesKHR> m(n);for(auto& x:m)x.sType=VK_STRUCTURE_TYPE_COOPERATIVE_MATRIX_PROPERTIES_KHR;CHECK(fn(c.pd,&n,m.data()));j["matrix_shapes"]=json::array();for(auto& x:m)j["matrix_shapes"].push_back({{"m",x.MSize},{"n",x.NSize},{"k",x.KSize},{"a",x.AType},{"b",x.BType},{"c",x.CType},{"result",x.ResultType},{"scope",x.scope},{"saturating",x.saturatingAccumulation}});}
 return j;
}
static uint32_t bits(float f){uint32_t x;memcpy(&x,&f,4);return x;}
int main(int argc,char** argv){
 try{
 Ctx c=createCtx();
 if(argc==1||std::string(argv[1])=="capabilities"){puts(caps(c).dump().c_str());return 0;}
 std::ifstream cf(argv[1]);json cfg;cf>>cfg;
 std::string family=cfg.at("family"),shader=cfg.at("shader");
 uint32_t wg=cfg.value("wg",64),groups=cfg.value("groups",256),width=cfg.value("width",1),chains=cfg.value("chains",1),loops=cfg.value("loops",128),n=cfg.value("n",1024),count=cfg.value("shared_count",1024),stride=cfg.value("stride",1),op=cfg.value("op",0);
 std::string dtype=cfg.value("dtype",std::string("fp32"));
 uint32_t M=cfg.value("m",1),N=cfg.value("matrix_n",1),K=cfg.value("k",1);
 const size_t threads=size_t(wg)*groups;
 bool half=dtype=="fp16",integer=dtype=="int8";
 if(family=="matrix"&&half)loops=std::min(loops,1024u/K);
 if(!c.timestampBits || wg>c.props.limits.maxComputeWorkGroupInvocations || groups>c.props.limits.maxComputeWorkGroupCount[0])throw std::runtime_error("unsupported launch/timestamps");
 if(family=="shared" && (uint64_t(count)*width*(half?2:4)>c.props.limits.maxComputeSharedMemorySize || (op && uint64_t(wg)*stride>count)))throw std::runtime_error("unsupported shared footprint or nonunique write mapping");
 size_t sizes[4]={std::max<size_t>(n*width*4ull,threads*width*4),std::max<size_t>(n*width*4ull,threads*width*4),16,std::max<size_t>(n*width*4ull,threads*width*chains*4)};
 if(family=="shared")sizes[0]=std::max<size_t>(sizes[0],count*width*4ull);
 if(family=="matrix"){sizes[0]=M*K*(integer?1:2);sizes[1]=K*N*(integer?1:2);sizes[3]=groups*chains*M*N*(half?2:4);}
 Buf b[4];for(int i=0;i<4;i++){if(sizes[i]>c.props.limits.maxStorageBufferRange)throw std::runtime_error("maxStorageBufferRange");b[i]=makeBuf(c,sizes[i]);memset(b[i].p,0,sizes[i]);}
 for(int z=0;z<2;z++)for(size_t i=0;i<sizes[z]/4;i++)((float*)b[z].p)[i]=float((i*13+z*7)%127)*0.0625f;
 if(family=="alu")for(size_t i=0;i<threads*width;i++){((float*)b[0].p)[i]=i%2?0.25f:0.5f;((float*)b[1].p)[i]=float(i%7+1)*0.03125f;}
 if(family=="shared")for(size_t i=0;i<sizes[0]/4;i++)((float*)b[0].p)[i]=float(i%17);
 if(family=="dot")for(size_t i=0;i<threads;i++){((uint32_t*)b[0].p)[i]=0x01020304u+uint32_t(i%3);((uint32_t*)b[1].p)[i]=0x01020102u;}
 if(family=="matrix")for(int z=0;z<2;z++){if(integer)memset(b[z].p,1,sizes[z]);else for(size_t i=0;i<sizes[z]/2;i++)((uint16_t*)b[z].p)[i]=f2h(0.0625f);}
 memset(b[3].p,0xff,sizes[3]);
 VkDescriptorSetLayoutBinding binds[4];for(uint32_t i=0;i<4;i++)binds[i]={i,VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1,VK_SHADER_STAGE_COMPUTE_BIT,nullptr};
 VkDescriptorSetLayoutCreateInfo dl{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};dl.bindingCount=4;dl.pBindings=binds;VkDescriptorSetLayout dsl;CHECK(vkCreateDescriptorSetLayout(c.dev,&dl,nullptr,&dsl));
 VkPushConstantRange pr{VK_SHADER_STAGE_COMPUTE_BIT,0,16};VkPipelineLayoutCreateInfo plc{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};plc.setLayoutCount=1;plc.pSetLayouts=&dsl;plc.pushConstantRangeCount=1;plc.pPushConstantRanges=&pr;VkPipelineLayout pl;CHECK(vkCreatePipelineLayout(c.dev,&plc,nullptr,&pl));
 VkPipeline pipe=VK_NULL_HANDLE;VkShaderModule sm=VK_NULL_HANDLE;
 if(family!="copy"){
 std::ifstream sf(shader,std::ios::binary|std::ios::ate);if(!sf)throw std::runtime_error("shader not found");size_t len=sf.tellg();sf.seekg(0);std::vector<uint32_t> spv(len/4);sf.read((char*)spv.data(),len);
 VkShaderModuleCreateInfo sci{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};sci.codeSize=len;sci.pCode=spv.data();CHECK(vkCreateShaderModule(c.dev,&sci,nullptr,&sm));
 uint32_t values[]={wg,count,stride};VkSpecializationMapEntry entries[]={{0,0,4},{1,4,4},{2,8,4}};VkSpecializationInfo spec{3,entries,12,values};
 VkPipelineShaderStageRequiredSubgroupSizeCreateInfo rss{VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_REQUIRED_SUBGROUP_SIZE_CREATE_INFO};rss.requiredSubgroupSize=g_subgroup;
 VkComputePipelineCreateInfo pci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};pci.flags=VK_PIPELINE_CREATE_CAPTURE_STATISTICS_BIT_KHR|VK_PIPELINE_CREATE_CAPTURE_INTERNAL_REPRESENTATIONS_BIT_KHR;pci.layout=pl;pci.stage={VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,(family=="matrix"&&g_sgctl)?&rss:nullptr,0,VK_SHADER_STAGE_COMPUTE_BIT,sm,"main",&spec};
 CHECK(vkCreateComputePipelines(c.dev,VK_NULL_HANDLE,1,&pci,nullptr,&pipe));}

 auto props=(PFN_vkGetPipelineExecutablePropertiesKHR)vkGetDeviceProcAddr(c.dev,"vkGetPipelineExecutablePropertiesKHR");
 auto stats=(PFN_vkGetPipelineExecutableStatisticsKHR)vkGetDeviceProcAddr(c.dev,"vkGetPipelineExecutableStatisticsKHR");
 auto reps=(PFN_vkGetPipelineExecutableInternalRepresentationsKHR)vkGetDeviceProcAddr(c.dev,"vkGetPipelineExecutableInternalRepresentationsKHR");
 VkPipelineInfoKHR info{VK_STRUCTURE_TYPE_PIPELINE_INFO_KHR};info.pipeline=pipe;uint32_t num=0;CHECK(props(c.dev,&info,&num,nullptr));
 std::vector<VkPipelineExecutablePropertiesKHR> pp(num);for(auto& v:pp)v.sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_PROPERTIES_KHR;CHECK(props(c.dev,&info,&num,pp.data()));
 json result={{"config",cfg},{"executables",json::array()}};
 for(uint32_t i=0;i<num;i++){
  VkPipelineExecutableInfoKHR ei{VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INFO_KHR};ei.pipeline=pipe;ei.executableIndex=i;
  uint32_t ns=0;CHECK(stats(c.dev,&ei,&ns,nullptr));std::vector<VkPipelineExecutableStatisticKHR> ss(ns);for(auto& v:ss)v.sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_STATISTIC_KHR;CHECK(stats(c.dev,&ei,&ns,ss.data()));
  json ex={{"name",pp[i].name},{"description",pp[i].description},{"subgroup_size",pp[i].subgroupSize},{"statistics",json::array()},{"representations",json::array()}};
  for(auto& st:ss){json value;switch(st.format){case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_BOOL32_KHR:value=bool(st.value.b32);break;case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_INT64_KHR:value=st.value.i64;break;case VK_PIPELINE_EXECUTABLE_STATISTIC_FORMAT_UINT64_KHR:value=st.value.u64;break;default:value=st.value.f64;break;}ex["statistics"].push_back({{"name",st.name},{"description",st.description},{"value",value}});}
  uint32_t nr=0;CHECK(reps(c.dev,&ei,&nr,nullptr));std::vector<VkPipelineExecutableInternalRepresentationKHR> rr(nr);for(auto& v:rr)v.sType=VK_STRUCTURE_TYPE_PIPELINE_EXECUTABLE_INTERNAL_REPRESENTATION_KHR;
  if(nr){CHECK(reps(c.dev,&ei,&nr,rr.data()));std::vector<std::vector<char>> buffers(nr);for(uint32_t k=0;k<nr;k++){buffers[k].resize(rr[k].dataSize);rr[k].pData=buffers[k].data();}CHECK(reps(c.dev,&ei,&nr,rr.data()));for(uint32_t k=0;k<nr;k++)ex["representations"].push_back({{"name",rr[k].name},{"description",rr[k].description},{"text",rr[k].isText?std::string(buffers[k].data(),strnlen(buffers[k].data(),buffers[k].size())):std::string("binary representation")},{"bytes",rr[k].dataSize}});}
  result["executables"].push_back(ex);
 }
 puts(result.dump().c_str());vkDestroyDevice(c.dev,nullptr);vkDestroyInstance(c.inst,nullptr);return 0;
 }catch(const std::exception& e){fprintf(stderr,"ERROR %s\n",e.what());return 2;}
}
