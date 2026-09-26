cmake_minimum_required(VERSION 3.20)
project(igpu_roofline_runner LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# compile_commands.json for clangd (see ../.clangd); does not change the binaries.
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(JSON_INCLUDE ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/nlohmann_json/include)

# Android links the NDK's libvulkan. Host builds (Linux iGPU) need Vulkan headers,
# optionally from VULKAN_INCLUDE (e.g. a Vulkan-Headers checkout, no root needed),
# and the loader; a runtime-only libvulkan.so.1 without the dev symlink also works.
set(VULKAN_INCLUDE "" CACHE PATH "Directory containing vulkan/vulkan.h (host builds)")
if(ANDROID)
  set(VULKAN_LINK vulkan)
else()
  find_library(VULKAN_LINK NAMES vulkan libvulkan.so.1 REQUIRED)
endif()

# One runner source, two names: `roofline` for short runs, `roofline_sustained`
# for long runs (kept separate so a sustained run's binary is never replaced
# underneath it by a redeploy of the short-run binary).
foreach(target roofline roofline_sustained)
  add_executable(${target} src/roofline.cpp)
  target_include_directories(${target} PRIVATE ${JSON_INCLUDE} ${VULKAN_INCLUDE})
  target_compile_options(${target} PRIVATE -O2 -Wall -Wextra -Wno-missing-field-initializers)
  target_link_libraries(${target} PRIVATE ${VULKAN_LINK})
endforeach()

# Compiles pipelines with VK_KHR_pipeline_executable_properties and prints driver
# statistics / internal representations. Never used for timing.
add_executable(inspect src/inspect.cpp)
target_include_directories(inspect PRIVATE ${JSON_INCLUDE} ${VULKAN_INCLUDE})
target_compile_options(inspect PRIVATE -O2)
target_link_libraries(inspect PRIVATE ${VULKAN_LINK})
