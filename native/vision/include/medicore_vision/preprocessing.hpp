#pragma once

#include <cstdint>
#include <vector>

#include <opencv2/core/mat.hpp>

#include "medicore_vision/types.hpp"

namespace medicore::vision {

cv::Mat decode_image(const std::vector<std::uint8_t>& encoded);
cv::Mat to_grayscale_u8(const cv::Mat& image);
ImageMetadata inspect_image(const cv::Mat& image);
XRayQualityMetrics inspect_xray_quality(const cv::Mat& image);
cv::Mat robust_normalize_xray(const cv::Mat& image);
XRayTensor prepare_xray_tensor(
    const cv::Mat& image,
    const XRayPreprocessConfig& config = XRayPreprocessConfig{});
cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side = 2048);

}  // namespace medicore::vision
