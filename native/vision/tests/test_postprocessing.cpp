#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include "medicore_vision/postprocessing.hpp"

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

medicore::vision::TensorTransform letterbox_transform() {
    return medicore::vision::TensorTransform{
        .original_width = 100,
        .original_height = 50,
        .output_width = 200,
        .output_height = 200,
        .resized_width = 200,
        .resized_height = 100,
        .pad_left = 0,
        .pad_top = 50,
        .pad_right = 0,
        .pad_bottom = 50,
        .scale_x = 2.0,
        .scale_y = 2.0,
    };
}

void test_box_mapping_removes_letterbox_padding() {
    const auto transform = letterbox_transform();
    const auto mapped = medicore::vision::map_model_box_to_original(
        medicore::vision::BoxF{.x1 = 50.0, .y1 = 70.0, .x2 = 150.0, .y2 = 130.0},
        transform);

    require(std::abs(mapped.x1 - 25.0) < 1e-9, "mapped x1 mismatch");
    require(std::abs(mapped.y1 - 10.0) < 1e-9, "mapped y1 mismatch");
    require(std::abs(mapped.x2 - 75.0) < 1e-9, "mapped x2 mismatch");
    require(std::abs(mapped.y2 - 40.0) < 1e-9, "mapped y2 mismatch");

    bool threw = false;
    try {
        (void)medicore::vision::map_model_box_to_original(
            medicore::vision::BoxF{.x1 = 20.0, .y1 = 5.0, .x2 = 80.0, .y2 = 25.0},
            transform);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    require(threw, "box entirely in padding must fail closed");
}

void test_heatmap_maps_to_original_and_measures_region() {
    const auto transform = letterbox_transform();
    cv::Mat heatmap = cv::Mat::zeros(20, 20, CV_32FC1);
    cv::rectangle(heatmap, cv::Rect(5, 7, 10, 5), cv::Scalar(1.0F), cv::FILLED);

    medicore::vision::SpatialPostprocessConfig config;
    config.threshold = 0.5;
    config.min_component_area = 20;
    config.max_components = 8;
    config.normalize_minmax = false;
    config.pixel_spacing_row_mm = 0.5;
    config.pixel_spacing_col_mm = 0.25;

    const auto result = medicore::vision::postprocess_spatial_map(heatmap, transform, config);
    require(result.contract_version == "vision-post-v1/original-space", "postprocess contract mismatch");
    require(result.heatmap_original.type() == CV_32FC1, "heatmap dtype mismatch");
    require(result.mask_original.type() == CV_8UC1, "mask dtype mismatch");
    require(result.heatmap_original.cols == 100 && result.heatmap_original.rows == 50,
            "original heatmap shape mismatch");
    require(result.mask_original.cols == 100 && result.mask_original.rows == 50,
            "original mask shape mismatch");
    require(result.regions.size() == 1, "expected one mapped hot region");

    const auto& region = result.regions.front();
    require(region.x >= 20 && region.x <= 30, "mapped region x outside expected range");
    require(region.y >= 7 && region.y <= 15, "mapped region y outside expected range");
    require(region.width >= 45 && region.width <= 60, "mapped region width outside expected range");
    require(region.height >= 20 && region.height <= 30, "mapped region height outside expected range");
    require(region.area_pixels > 500, "mapped region area unexpectedly small");
    require(region.mean_score >= 0.5 && region.mean_score <= 1.0, "mean score outside thresholded range");
    require(region.peak_score > 0.95, "peak score should preserve hot activation");
    require(region.area_mm2.has_value(), "physical area should be available with spacing");
    require(std::abs(*region.area_mm2 - static_cast<double>(region.area_pixels) * 0.125) < 1e-6,
            "physical area calculation mismatch");
    require(region.bbox_width_mm.has_value() && region.bbox_height_mm.has_value(),
            "physical bbox dimensions missing");
}

void test_small_components_are_filtered_and_regions_sorted() {
    medicore::vision::TensorTransform transform{
        .original_width = 100,
        .original_height = 100,
        .output_width = 100,
        .output_height = 100,
        .resized_width = 100,
        .resized_height = 100,
        .pad_left = 0,
        .pad_top = 0,
        .pad_right = 0,
        .pad_bottom = 0,
        .scale_x = 1.0,
        .scale_y = 1.0,
    };

    cv::Mat heatmap = cv::Mat::zeros(100, 100, CV_32FC1);
    cv::rectangle(heatmap, cv::Rect(10, 10, 10, 10), cv::Scalar(0.8F), cv::FILLED);
    cv::rectangle(heatmap, cv::Rect(50, 50, 12, 12), cv::Scalar(0.95F), cv::FILLED);
    cv::rectangle(heatmap, cv::Rect(80, 80, 2, 2), cv::Scalar(1.0F), cv::FILLED);

    medicore::vision::SpatialPostprocessConfig config;
    config.threshold = 0.5;
    config.min_component_area = 20;
    config.max_components = 2;
    config.normalize_minmax = false;

    const auto result = medicore::vision::postprocess_spatial_map(heatmap, transform, config);
    require(result.regions.size() == 2, "small component should be filtered");
    require(result.regions[0].peak_score > result.regions[1].peak_score,
            "regions should be sorted by activation strength");
    require(result.regions[0].x == 50 && result.regions[0].y == 50,
            "strongest region should be first");
}

void test_invalid_spatial_map_fails_closed() {
    const auto transform = letterbox_transform();
    cv::Mat heatmap = cv::Mat::zeros(2, 2, CV_32FC1);
    heatmap.at<float>(0, 0) = std::numeric_limits<float>::quiet_NaN();

    bool threw = false;
    try {
        (void)medicore::vision::postprocess_spatial_map(heatmap, transform);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    require(threw, "NaN heatmap must fail closed");
}

}  // namespace

int main() {
    try {
        test_box_mapping_removes_letterbox_padding();
        test_heatmap_maps_to_original_and_measures_region();
        test_small_components_are_filtered_and_regions_sorted();
        test_invalid_spatial_map_fails_closed();
        std::cout << "Vision post-processing tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Vision post-processing test failure: " << error.what() << '\n';
        return 1;
    }
}
