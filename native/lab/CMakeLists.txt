cmake_minimum_required(VERSION 3.20)
project(medicore_lab LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(pybind11 CONFIG REQUIRED)

add_library(
    medicore_lab_core
    STATIC
    src/lab_core.cpp
)
set_target_properties(medicore_lab_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(
    medicore_lab_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

pybind11_add_module(
    medicore_lab
    src/bindings.cpp
)
target_link_libraries(
    medicore_lab
    PRIVATE
        medicore_lab_core
)
target_compile_definitions(
    medicore_lab
    PRIVATE
        MEDICORE_LAB_VERSION="1.0.0"
)

enable_testing()
add_executable(
    medicore_lab_core_tests
    tests/test_lab_core.cpp
)
target_link_libraries(
    medicore_lab_core_tests
    PRIVATE
        medicore_lab_core
)
add_test(NAME medicore_lab_core COMMAND medicore_lab_core_tests)
