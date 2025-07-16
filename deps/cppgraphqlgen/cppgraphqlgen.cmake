# No special platform flags are needed for cppgraphqlgen (as of now)
set(_cppgraphqlgen_platform_flags
    -DCPPGRAPHQLGEN_BUILD_TESTS=OFF
    -DCPPGRAPHQLGEN_BUILD_SAMPLES=OFF
    -DCMAKE_POSITION_INDEPENDENT_CODE=ON
)

# Ensure static build
if (BUILD_SHARED_LIBS)
  set(_cppgraphqlgen_static OFF)
else()
  set(_cppgraphqlgen_static ON)
endif()

orcaslicer_add_cmake_project(cppgraphqlgen
  GIT_REPOSITORY https://github.com/microsoft/cppgraphqlgen.git
  GIT_TAG v3.6.0
  DEPENDS dep_RAPIDJSON dep_GTEST dep_PEGTL
  CMAKE_ARGS
    -DCPPGRAPHQLGEN_STATIC=${_cppgraphqlgen_static}
    ${_cppgraphqlgen_platform_flags} 
)

if (MSVC)
    add_debug_dep(dep_cppgraphqlgen)
endif()
