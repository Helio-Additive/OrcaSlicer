if (APPLE)
    message(STATUS "Compiling cppgraphqlgen for macOS ${CMAKE_SYSTEM_VERSION}.")
    orcaslicer_add_cmake_project(cppgraphqlgen
        GIT_REPOSITORY https://github.com/microsoft/cppgraphqlgen.git
        GIT_TAG v3.7.1
        UPDATE_COMMAND ${GIT_EXECUTABLE} submodule update --init --recursive
        CMAKE_ARGS
            -DGRAPHQL_BUILD_JSON=ON
            -DGRAPHQL_BUILD_TESTS=OFF
            -DGRAPHQL_UPDATE_SAMPLES=OFF
            -DGRAPHQL_BUILD_SCHEMAGEN=ON
            -DGRAPHQL_BUILD_CLIENTGEN=ON
            -DGRAPHQL_BUILD_TESTS=OFF
            -DGRAPHQL_USE_RAPIDJSON=OFF
            -DBUILD_SHARED_LIBS=OFF
    )
else()
    orcaslicer_add_cmake_project(cppgraphqlgen
        GIT_REPOSITORY https://github.com/microsoft/cppgraphqlgen.git
        GIT_TAG v3.7.1
        UPDATE_COMMAND ${GIT_EXECUTABLE} submodule update --init --recursive
        CMAKE_ARGS
            -DGRAPHQL_BUILD_JSON=ON
            -DGRAPHQL_BUILD_TESTS=OFF
            -DGRAPHQL_UPDATE_SAMPLES=OFF
            -DGRAPHQL_BUILD_SCHEMAGEN=ON
            -DGRAPHQL_BUILD_CLIENTGEN=ON
            -DGRAPHQL_BUILD_TESTS=OFF
            -DGRAPHQL_USE_RAPIDJSON=OFF
            -DBUILD_SHARED_LIBS=OFF
    )
endif()
