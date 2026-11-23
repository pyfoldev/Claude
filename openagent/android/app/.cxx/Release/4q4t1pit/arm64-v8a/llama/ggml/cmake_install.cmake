# Install script for directory: /home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml

# Set the install prefix
if(NOT DEFINED CMAKE_INSTALL_PREFIX)
  set(CMAKE_INSTALL_PREFIX "/usr/local")
endif()
string(REGEX REPLACE "/$" "" CMAKE_INSTALL_PREFIX "${CMAKE_INSTALL_PREFIX}")

# Set the install configuration name.
if(NOT DEFINED CMAKE_INSTALL_CONFIG_NAME)
  if(BUILD_TYPE)
    string(REGEX REPLACE "^[^A-Za-z0-9_]+" ""
           CMAKE_INSTALL_CONFIG_NAME "${BUILD_TYPE}")
  else()
    set(CMAKE_INSTALL_CONFIG_NAME "Release")
  endif()
  message(STATUS "Install configuration: \"${CMAKE_INSTALL_CONFIG_NAME}\"")
endif()

# Set the component getting installed.
if(NOT CMAKE_INSTALL_COMPONENT)
  if(COMPONENT)
    message(STATUS "Install component: \"${COMPONENT}\"")
    set(CMAKE_INSTALL_COMPONENT "${COMPONENT}")
  else()
    set(CMAKE_INSTALL_COMPONENT)
  endif()
endif()

# Install shared libraries without execute permission?
if(NOT DEFINED CMAKE_INSTALL_SO_NO_EXE)
  set(CMAKE_INSTALL_SO_NO_EXE "1")
endif()

# Is this installation the result of a crosscompile?
if(NOT DEFINED CMAKE_CROSSCOMPILING)
  set(CMAKE_CROSSCOMPILING "TRUE")
endif()

# Set default install directory permissions.
if(NOT DEFINED CMAKE_OBJDUMP)
  set(CMAKE_OBJDUMP "/tmp/claude-0/sdk/ndk/27.2.12479018/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objdump")
endif()

if(NOT CMAKE_INSTALL_LOCAL_ONLY)
  # Include the install script for the subdirectory.
  include("/home/user/Claude/openagent/android/app/.cxx/Release/4q4t1pit/arm64-v8a/llama/ggml/src/cmake_install.cmake")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE STATIC_LIBRARY FILES "/home/user/Claude/openagent/android/app/.cxx/Release/4q4t1pit/arm64-v8a/llama/ggml/src/libggml.a")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/include" TYPE FILE FILES
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-cpu.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-alloc.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-backend.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-blas.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-cann.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-cpp.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-cuda.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-opt.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-metal.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-rpc.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-virtgpu.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-sycl.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-vulkan.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-webgpu.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-zendnn.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/ggml-openvino.h"
    "/home/user/Claude/openagent/android/app/src/main/cpp/llama/ggml/include/gguf.h"
    )
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib" TYPE STATIC_LIBRARY FILES "/home/user/Claude/openagent/android/app/.cxx/Release/4q4t1pit/arm64-v8a/llama/ggml/src/libggml-base.a")
endif()

if("x${CMAKE_INSTALL_COMPONENT}x" STREQUAL "xUnspecifiedx" OR NOT CMAKE_INSTALL_COMPONENT)
  file(INSTALL DESTINATION "${CMAKE_INSTALL_PREFIX}/lib/cmake/ggml" TYPE FILE FILES
    "/home/user/Claude/openagent/android/app/.cxx/Release/4q4t1pit/arm64-v8a/llama/ggml/ggml-config.cmake"
    "/home/user/Claude/openagent/android/app/.cxx/Release/4q4t1pit/arm64-v8a/llama/ggml/ggml-config-version.cmake"
    )
endif()

