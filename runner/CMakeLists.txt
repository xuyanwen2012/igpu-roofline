cmake_minimum_required(VERSION 3.20)
project(igpu_roofline_runner LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(JSON_INCLUDE ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/nlohmann_json/include)

# One runner source, two names: `roofline` for short runs, `roofline_sustained`
# for long runs (kept separate so a sustained run's binary is never replaced
# underneath it by a redeploy of the short-run binary).
foreach(target roofline roofline_sustained)
  add_executable(${target} src/roofline.cpp)
  target_include_directories(${target} PRIVATE ${JSON_INCLUDE})
  target_compile_options(${target} PRIVATE -O2 -Wall -Wextra -Wno-missing-field-initializers)
  target_link_libraries(${target} PRIVATE vulkan)
endforeach()

# Compiles pipelines with VK_KHR_pipeline_executable_properties and prints driver
# statistics / internal representations. Never used for timing.
add_executable(inspect src/inspect.cpp)
target_include_directories(inspect PRIVATE ${JSON_INCLUDE})
target_compile_options(inspect PRIVATE -O2)
target_link_libraries(inspect PRIVATE vulkan)
