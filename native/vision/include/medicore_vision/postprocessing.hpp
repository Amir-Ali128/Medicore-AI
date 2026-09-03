#pragma once

#include <optional>
#include <string>
#include <vector>

#include <opencv2/core/mat.hpp>

#include "medicore_vision/types.hpp"

namespace medicore::vision {

inline constexpr const char* kVisionPostprocessContract =
    "vision-post-v1/original-space";

struct BoxF {
    double x1{0.0};
    double y1{0.0};
    double x2{0.0};
    double y2{0.0};
};

struct RegionMeasurement {
    int component_id{0};
    int x{0};
    int y{0};
    int width{0};
    int height{0};
    int area_pixels{0};
    double area_fraction{0.0};
    double centroid_x{0.0};
    double centroid_y{0.0};
    double mean_score{0.0};
    double peak_score{0.0};
    std::optional<double> area_mm2{};
    std::optional<double> bbox_width_mm{};
    std::optional<double> bbox_height_mm{};
};

struct SpatialPostprocessConfig {
    double threshold{0.5};
    int min_component_area{16};
    int max_components{32};
    bool normalize_minmax{true};
    std::optional<double> pixel_spacing_row_mm{};
    std::optional<double> pixel_spacing_col_mm{};
};

struct SpatialPostprocessResult {
    cv::Mat heatmap_original{};  // CV_32FC1, normalized [0,1]
    cv::Mat mask_original{};     // CV_8UC1, values 0/255
    std::vector<RegionMeasurement> regions{};
    std::string contract_version{kVisionPostprocessContract};
};

void validate_tensor_transform(const TensorTransform& transform);

BoxF map_model_box_to_original(
    const BoxF& model_box,
    const TensorTransform& transform,
    bool clip = true);

SpatialPostprocessResult postprocess_spatial_map(
    const cv::Mat& spatial_map,
    const TensorTransform& transform,
    const SpatialPostprocessConfig& config = SpatialPostprocessConfig{});

}  // namespace medicore::vision
