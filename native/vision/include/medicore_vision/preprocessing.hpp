#pragma once

#include <cstdint>
#include <vector>

#include <opencv2/core/mat.hpp>

#include "medicore_vision/types.hpp"

namespace medicore::vision {

cv::Mat decode_image(const std::vector<std::uint8_t>& encoded);
ImageMetadata inspect_image(const cv::Mat& image);
ImageQualityMetrics assess_chest_xray_quality(const cv::Mat& image);
cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side = 2048);
cv::Mat prepare_chest_xray_tensor(const cv::Mat& image, int target_size = 1024);

}  // namespace medicore::vision
