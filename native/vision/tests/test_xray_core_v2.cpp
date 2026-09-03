#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

#include <opencv2/core.hpp>

#include "medicore_vision/preprocessing.hpp"

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void test_quality_metrics_detect_uniform_image() {
    cv::Mat image(300, 300, CV_8UC1, cv::Scalar(80));
    const auto quality = medicore::vision::inspect_xray_quality(image);
    require(quality.width == 300 && quality.height == 300, "quality dimensions mismatch");
    require(quality.robust_dynamic_range == 0.0, "uniform image must have zero robust range");
    require(quality.stddev_intensity == 0.0, "uniform image must have zero stddev");
    require(
        std::find(quality.technical_flags.begin(), quality.technical_flags.end(), "NEAR_UNIFORM") !=
            quality.technical_flags.end(),
        "uniform image should be flagged");
}

void test_robust_normalization_spans_range() {
    cv::Mat image(256, 256, CV_8UC1);
    for (int row = 0; row < image.rows; ++row) {
        auto* pixels = image.ptr<std::uint8_t>(row);
        for (int col = 0; col < image.cols; ++col) {
            pixels[col] = static_cast<std::uint8_t>(col);
        }
    }
    const cv::Mat normalized = medicore::vision::robust_normalize_xray(image);
    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(normalized, &min_value, &max_value);
    require(min_value == 0.0, "normalized minimum should be zero");
    require(max_value == 255.0, "normalized maximum should be 255");
}

void test_tensor_contract_and_letterbox_geometry() {
    cv::Mat image(100, 200, CV_8UC1);
    for (int row = 0; row < image.rows; ++row) {
        auto* pixels = image.ptr<std::uint8_t>(row);
        for (int col = 0; col < image.cols; ++col) {
            pixels[col] = static_cast<std::uint8_t>((row + col) % 256);
        }
    }

    const medicore::vision::XRayPreprocessConfig config{
        .target_width = 64,
        .target_height = 64,
        .preserve_aspect_ratio = true,
        .pad_value = 0,
    };
    const auto tensor = medicore::vision::prepare_xray_tensor(image, config);

    require(tensor.shape == std::array<std::int64_t, 4>{1, 1, 64, 64}, "NCHW shape mismatch");
    require(tensor.values.size() == 64U * 64U, "tensor element count mismatch");
    require(tensor.contract_version == "xray-core-v2/nchw-f32-0-1", "contract version mismatch");
    require(tensor.transform.resized_width == 64, "letterbox resized width mismatch");
    require(tensor.transform.resized_height == 32, "letterbox resized height mismatch");
    require(tensor.transform.pad_top == 16 && tensor.transform.pad_bottom == 16, "letterbox vertical padding mismatch");
    for (const float value : tensor.values) {
        require(value >= 0.0F && value <= 1.0F, "tensor value outside [0,1]");
    }
}

void test_invalid_tensor_dimensions_rejected() {
    cv::Mat image(64, 64, CV_8UC1, cv::Scalar(10));
    medicore::vision::XRayPreprocessConfig config;
    config.target_width = 16;
    bool threw = false;
    try {
        static_cast<void>(medicore::vision::prepare_xray_tensor(image, config));
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    require(threw, "invalid tensor dimensions should throw");
}

}  // namespace

int main() {
    try {
        test_quality_metrics_detect_uniform_image();
        test_robust_normalization_spans_range();
        test_tensor_contract_and_letterbox_geometry();
        test_invalid_tensor_dimensions_rejected();
        std::cout << "X-Ray Core v2 tests passed\n";
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << "X-Ray Core v2 test failure: " << exc.what() << '\n';
        return 1;
    }
}
