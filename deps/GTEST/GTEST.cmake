orcaslicer_add_cmake_project(GTEST
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG v1.17.0
  CMAKE_ARGS
    -DBUILD_GMOCK=OFF
    -DBUILD_GTEST=ON
    -DINSTALL_GTEST=ON
    -Dgtest_force_shared_crt=ON
)
