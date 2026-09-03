#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace medicore::vision {

struct ImageMetadata {
    int width{0};
    int height{0};
    int channels{0};
    double mean_intensity{0.0};
    double stddev_intensity{0.0};
    std::uint8_t min_intensity{0};
    std::uint8_t max_intensity{0};
};

struct XRayQualityMetrics {
    int width{0};
    int height{0};
    double mean_intensity{0.0};
    double stddev_intensity{0.0};
    double p01_intensity{0.0};
    double p99_intensity{0.0};
    double robust_dynamic_range{0.0};
    double low_clip_ratio{0.0};
    double high_clip_ratio{0.0};
    double entropy_bits{0.0};
    double laplacian_variance{0.0};
    std::vector<std::string> technical_flags{};
};

struct XRayPreprocessConfig {
    int target_width{1024};
    int target_height{1024};
    bool preserve_aspect_ratio{true};
    std::uint8_t pad_value{0};
};

struct TensorTransform {
    int original_width{0};
    int original_height{0};
    int output_width{0};
    int output_height{0};
    int resized_width{0};
    int resized_height{0};
    int pad_left{0};
    int pad_top{0};
    int pad_right{0};
    int pad_bottom{0};
    double scale_x{1.0};
    double scale_y{1.0};
};

struct XRayTensor {
    std::vector<float> values{};
    std::array<std::int64_t, 4> shape{1, 1, 0, 0};
    TensorTransform transform{};
    XRayQualityMetrics quality{};
    std::string contract_version{"xray-core-v2/nchw-f32-0-1"};
};

}  // namespace medicore::vision
