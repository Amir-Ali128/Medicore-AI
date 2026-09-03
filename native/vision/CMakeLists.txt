cmake_minimum_required(VERSION 3.20)
project(medicore_vision LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenCV REQUIRED COMPONENTS core imgcodecs imgproc)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(
    medicore_vision
    src/bindings.cpp
    src/preprocessing.cpp
)

target_include_directories(
    medicore_vision
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(
    medicore_vision
    PRIVATE
        ${OpenCV_LIBS}
)

target_compile_definitions(
    medicore_vision
    PRIVATE
        MEDICORE_VISION_VERSION="0.1.0"
)
