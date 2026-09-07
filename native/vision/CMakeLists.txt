cmake_minimum_required(VERSION 3.20)
project(medicore_vision LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenCV REQUIRED COMPONENTS core imgcodecs imgproc)
find_package(pybind11 CONFIG REQUIRED)
find_package(DCMTK REQUIRED)

# ONNX Runtime C++ is optional. CI can compile the stub contract without the
# external runtime, while production builds may enable the native execution hot path
# by installing ONNX Runtime and/or setting ONNXRUNTIME_ROOT.
find_path(
    ONNXRUNTIME_INCLUDE_DIR
    NAMES onnxruntime_cxx_api.h
    HINTS $ENV{ONNXRUNTIME_ROOT}
    PATH_SUFFIXES include include/onnxruntime/core/session onnxruntime/core/session
)
find_library(
    ONNXRUNTIME_LIBRARY
    NAMES onnxruntime
    HINTS $ENV{ONNXRUNTIME_ROOT}
    PATH_SUFFIXES lib lib64
)

add_library(
    medicore_vision_core
    STATIC
    src/preprocessing.cpp
    src/inference_contract.cpp
    src/onnx_runtime.cpp
    src/dicom_engine.cpp
    src/postprocessing.cpp
    src/anatomy_gate.cpp
)
set_target_properties(medicore_vision_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(
    medicore_vision_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${DCMTK_INCLUDE_DIRS}
)
target_link_libraries(
    medicore_vision_core
    PUBLIC
        ${OpenCV_LIBS}
        ${DCMTK_LIBRARIES}
)

if(ONNXRUNTIME_INCLUDE_DIR AND ONNXRUNTIME_LIBRARY)
    message(STATUS "MediCore native ONNX Runtime enabled")
    target_compile_definitions(medicore_vision_core PRIVATE MEDICORE_WITH_ONNXRUNTIME=1)
    target_include_directories(medicore_vision_core PRIVATE ${ONNXRUNTIME_INCLUDE_DIR})
    target_link_libraries(medicore_vision_core PUBLIC ${ONNXRUNTIME_LIBRARY})
else()
    message(STATUS "MediCore native ONNX Runtime not found; building safe stub backend")
endif()

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
        MEDICORE_VISION_VERSION="0.5.0"
)

pybind11_add_module(
    medicore_anatomy
    src/anatomy_bindings.cpp
)
target_link_libraries(
    medicore_anatomy
    PRIVATE
        medicore_vision_core
)
target_compile_definitions(
    medicore_anatomy
    PRIVATE
        MEDICORE_ANATOMY_VERSION="0.1.0"
)

pybind11_add_module(
    medicore_onnx
    src/onnx_bindings.cpp
)
target_link_libraries(
    medicore_onnx
    PRIVATE
        medicore_vision_core
)
target_compile_definitions(
    medicore_onnx
    PRIVATE
        MEDICORE_ONNX_VERSION="0.1.0"
)

install(
    TARGETS medicore_vision medicore_anatomy medicore_onnx
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .
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

add_executable(
    medicore_vision_dicom_tests
    tests/test_dicom_engine.cpp
)
target_link_libraries(
    medicore_vision_dicom_tests
    PRIVATE
        medicore_vision_core
)
add_test(NAME dicom_engine COMMAND medicore_vision_dicom_tests)

add_executable(
    medicore_vision_postprocessing_tests
    tests/test_postprocessing.cpp
)
target_link_libraries(
    medicore_vision_postprocessing_tests
    PRIVATE
        medicore_vision_core
)
add_test(NAME vision_postprocessing COMMAND medicore_vision_postprocessing_tests)

add_executable(
    medicore_vision_anatomy_gate_tests
    tests/test_anatomy_gate.cpp
)
target_link_libraries(
    medicore_vision_anatomy_gate_tests
    PRIVATE
        medicore_vision_core
)
add_test(NAME anatomy_confidence_gate COMMAND medicore_vision_anatomy_gate_tests)
