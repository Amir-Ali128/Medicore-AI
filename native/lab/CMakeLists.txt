cmake_minimum_required(VERSION 3.20)
project(medicore_lab LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MEDICORE_ENABLE_SANITIZERS "Enable ASan/UBSan for native lab targets" OFF)
option(MEDICORE_ENABLE_FUZZING "Build libFuzzer targets (Clang only)" OFF)

find_package(pybind11 CONFIG REQUIRED)

add_library(
    medicore_lab_core
    STATIC
    src/lab_core.cpp
    src/deterministic_core.cpp
    src/lab_extensions.cpp
    src/clinical_metrics.cpp
)
set_target_properties(medicore_lab_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(
    medicore_lab_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if(MEDICORE_ENABLE_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(medicore_lab_core PUBLIC -fno-omit-frame-pointer -fsanitize=address,undefined)
    target_link_options(medicore_lab_core PUBLIC -fno-omit-frame-pointer -fsanitize=address,undefined)
endif()

pybind11_add_module(medicore_lab src/bindings.cpp)
target_link_libraries(medicore_lab PRIVATE medicore_lab_core)
target_compile_definitions(medicore_lab PRIVATE MEDICORE_LAB_VERSION="1.5.0")

pybind11_add_module(medicore_lab_ext src/extensions_bindings.cpp)
target_link_libraries(medicore_lab_ext PRIVATE medicore_lab_core)
target_compile_definitions(medicore_lab_ext PRIVATE MEDICORE_LAB_EXT_VERSION="1.0.0")

install(
    TARGETS medicore_lab medicore_lab_ext
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .
)

enable_testing()
add_executable(medicore_lab_core_tests tests/test_lab_core.cpp)
target_link_libraries(medicore_lab_core_tests PRIVATE medicore_lab_core)
add_test(NAME medicore_lab_core COMMAND medicore_lab_core_tests)

add_executable(medicore_lab_deterministic_tests tests/test_deterministic_core.cpp)
target_link_libraries(medicore_lab_deterministic_tests PRIVATE medicore_lab_core)
add_test(NAME medicore_lab_deterministic COMMAND medicore_lab_deterministic_tests)

add_executable(medicore_lab_extensions_tests tests/test_lab_extensions.cpp)
target_link_libraries(medicore_lab_extensions_tests PRIVATE medicore_lab_core)
add_test(NAME medicore_lab_extensions COMMAND medicore_lab_extensions_tests)

add_executable(medicore_lab_canonical_trust_tests tests/test_canonical_trust.cpp)
target_link_libraries(medicore_lab_canonical_trust_tests PRIVATE medicore_lab_core)
add_test(NAME medicore_lab_canonical_trust COMMAND medicore_lab_canonical_trust_tests)

if(MEDICORE_ENABLE_FUZZING)
    if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "MEDICORE_ENABLE_FUZZING requires Clang/libFuzzer")
    endif()
    add_executable(medicore_lab_reference_fuzz fuzz/reference_parser_fuzz.cpp)
    target_link_libraries(medicore_lab_reference_fuzz PRIVATE medicore_lab_core)
    target_compile_options(medicore_lab_reference_fuzz PRIVATE -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
    target_link_options(medicore_lab_reference_fuzz PRIVATE -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
endif()
