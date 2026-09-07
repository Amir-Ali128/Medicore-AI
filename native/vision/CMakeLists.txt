cmake_minimum_required(VERSION 3.20)
project(medicore_vision LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(MEDICORE_ENABLE_SANITIZERS "Enable ASan/UBSan for native vision targets" OFF)
option(MEDICORE_ENABLE_FUZZING "Build libFuzzer DICOM target (Clang only)" OFF)

find_package(OpenCV REQUIRED COMPONENTS core imgcodecs imgproc)
find_package(pybind11 CONFIG REQUIRED)
find_package(DCMTK REQUIRED)

# Optional DCMTK compressed-pixel codecs. RLE ships with dcmdata; JPEG/JPEG-LS
# are enabled only when both their headers and libraries are present.
find_path(DCMJPEG_INCLUDE_DIR NAMES dcmtk/dcmjpeg/djdecode.h PATHS ${DCMTK_INCLUDE_DIRS})
find_library(DCMJPEG_LIBRARY NAMES dcmjpeg)
find_path(DCMJPLS_INCLUDE_DIR NAMES dcmtk/dcmjpls/djdecode.h PATHS ${DCMTK_INCLUDE_DIRS})
find_library(DCMJPLS_LIBRARY NAMES dcmjpls)

# ONNX Runtime C++ is optional. CI can compile the stub contract without the
# external runtime; production builds enable the hot path when ORT is installed.
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
    src/dicom_codecs.cpp
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

if(DCMJPEG_INCLUDE_DIR AND DCMJPEG_LIBRARY)
    message(STATUS "MediCore DICOM JPEG decoder enabled")
    target_compile_definitions(medicore_vision_core PRIVATE MEDICORE_WITH_DCMJPEG=1)
    target_include_directories(medicore_vision_core PRIVATE ${DCMJPEG_INCLUDE_DIR})
    target_link_libraries(medicore_vision_core PUBLIC ${DCMJPEG_LIBRARY})
else()
    message(STATUS "MediCore DICOM JPEG decoder unavailable; JPEG transfer syntaxes fail closed")
endif()

if(DCMJPLS_INCLUDE_DIR AND DCMJPLS_LIBRARY)
    message(STATUS "MediCore DICOM JPEG-LS decoder enabled")
    target_compile_definitions(medicore_vision_core PRIVATE MEDICORE_WITH_DCMJPLS=1)
    target_include_directories(medicore_vision_core PRIVATE ${DCMJPLS_INCLUDE_DIR})
    target_link_libraries(medicore_vision_core PUBLIC ${DCMJPLS_LIBRARY})
else()
    message(STATUS "MediCore DICOM JPEG-LS decoder unavailable; JPEG-LS transfer syntaxes fail closed")
endif()

if(ONNXRUNTIME_INCLUDE_DIR AND ONNXRUNTIME_LIBRARY)
    message(STATUS "MediCore native ONNX Runtime enabled")
    target_compile_definitions(medicore_vision_core PRIVATE MEDICORE_WITH_ONNXRUNTIME=1)
    target_include_directories(medicore_vision_core PRIVATE ${ONNXRUNTIME_INCLUDE_DIR})
    target_link_libraries(medicore_vision_core PUBLIC ${ONNXRUNTIME_LIBRARY})
else()
    message(STATUS "MediCore native ONNX Runtime not found; building safe stub backend")
endif()

if(MEDICORE_ENABLE_SANITIZERS AND CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(medicore_vision_core PUBLIC -fno-omit-frame-pointer -fsanitize=address,undefined)
    target_link_options(medicore_vision_core PUBLIC -fno-omit-frame-pointer -fsanitize=address,undefined)
endif()

pybind11_add_module(medicore_vision src/bindings.cpp)
target_link_libraries(medicore_vision PRIVATE medicore_vision_core)
target_compile_definitions(medicore_vision PRIVATE MEDICORE_VISION_VERSION="0.6.0")

pybind11_add_module(medicore_anatomy src/anatomy_bindings.cpp)
target_link_libraries(medicore_anatomy PRIVATE medicore_vision_core)
target_compile_definitions(medicore_anatomy PRIVATE MEDICORE_ANATOMY_VERSION="0.1.0")

pybind11_add_module(medicore_onnx src/onnx_bindings.cpp)
target_link_libraries(medicore_onnx PRIVATE medicore_vision_core)
target_compile_definitions(medicore_onnx PRIVATE MEDICORE_ONNX_VERSION="0.2.0")

install(
    TARGETS medicore_vision medicore_anatomy medicore_onnx
    LIBRARY DESTINATION .
    RUNTIME DESTINATION .
)

enable_testing()
add_executable(medicore_vision_core_tests tests/test_xray_core_v2.cpp)
target_link_libraries(medicore_vision_core_tests PRIVATE medicore_vision_core)
add_test(NAME xray_core_v2 COMMAND medicore_vision_core_tests)

add_executable(medicore_vision_inference_contract_tests tests/test_inference_contract.cpp)
target_link_libraries(medicore_vision_inference_contract_tests PRIVATE medicore_vision_core)
add_test(NAME onnx_inference_contract COMMAND medicore_vision_inference_contract_tests)

add_executable(medicore_vision_dicom_tests tests/test_dicom_engine.cpp)
target_link_libraries(medicore_vision_dicom_tests PRIVATE medicore_vision_core)
add_test(NAME dicom_engine COMMAND medicore_vision_dicom_tests)

add_executable(medicore_vision_dicom_codec_tests tests/test_dicom_codecs.cpp)
target_link_libraries(medicore_vision_dicom_codec_tests PRIVATE medicore_vision_core)
add_test(NAME dicom_codecs COMMAND medicore_vision_dicom_codec_tests)

add_executable(medicore_vision_postprocessing_tests tests/test_postprocessing.cpp)
target_link_libraries(medicore_vision_postprocessing_tests PRIVATE medicore_vision_core)
add_test(NAME vision_postprocessing COMMAND medicore_vision_postprocessing_tests)

add_executable(medicore_vision_anatomy_gate_tests tests/test_anatomy_gate.cpp)
target_link_libraries(medicore_vision_anatomy_gate_tests PRIVATE medicore_vision_core)
add_test(NAME anatomy_confidence_gate COMMAND medicore_vision_anatomy_gate_tests)

if(MEDICORE_ENABLE_FUZZING)
    if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "MEDICORE_ENABLE_FUZZING requires Clang/libFuzzer")
    endif()
    add_executable(medicore_dicom_fuzz fuzz/dicom_fuzz.cpp)
    target_link_libraries(medicore_dicom_fuzz PRIVATE medicore_vision_core)
    target_compile_options(medicore_dicom_fuzz PRIVATE -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
    target_link_options(medicore_dicom_fuzz PRIVATE -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
endif()
