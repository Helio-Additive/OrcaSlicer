orcaslicer_add_cmake_project(CPR
  GIT_REPOSITORY https://github.com/libcpr/cpr.git
  GIT_TAG 1.11.2
  CMAKE_ARGS
    -DCPR_BUILD_TESTS=OFF
    -DCPR_BUILD_EXAMPLES=OFF
    -DCPR_USE_SYSTEM_CURL=OFF
    -DCPR_FORCE_USE_SYSTEM_CURL=OFF
)
