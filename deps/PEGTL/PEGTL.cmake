orcaslicer_add_cmake_project(PEGTL
  GIT_REPOSITORY https://github.com/taocpp/PEGTL.git
  GIT_TAG 3.2.7
  CMAKE_ARGS
    -DPEGTL_BUILD_TESTS=OFF
    -DPEGTL_BUILD_EXAMPLES=OFF
)