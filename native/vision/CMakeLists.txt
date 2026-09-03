cmake_minimum_required(VERSION 3.20)
project(medicore_vision LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenCV REQUIRED COMPONENTS core imgcodecs imgproc)
find_package(pybind11 CONFIG REQUIRED)

add_library(
    medicore_vision_core
    STATIC
    src/preprocessing.cpp
    src/inference_contract.cpp
)
set_target_properties(medicore_vision_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(
    medicore_vision_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)
target_link_libraries(
    medicore_vision_core
    PUBLIC
        ${OpenCV_LIBS}
)

pybind11_add_module(
    medicore_vision
    src/bindings.cpp
)
target_link_libraries(
    medicore_vision
    PRIVATE
        medicore_vision_core
)
target_compile_definitions(
    medicore_vision
    PRIVATE
        MEDICORE_VISION_VERSION="0.3.0"
)

enable_testing()
add_executable(
    medicore_vision_core_tests
    tests/test_xray_core_v2.cpp
)
target_link_libraries(
    medicore_vision_core_tests
    PRIVATE
        medicore_vision_core
)
add_test(NAME xray_core_v2 COMMAND medicore_vision_core_tests)

add_executable(
    medicore_vision_inference_contract_tests
    tests/test_inference_contract.cpp
)
target_link_libraries(
    medicore_vision_inference_contract_tests
    PRIVATE
        medicore_vision_core
)
add_test(NAME onnx_inference_contract COMMAND medicore_vision_inference_contract_tests)
