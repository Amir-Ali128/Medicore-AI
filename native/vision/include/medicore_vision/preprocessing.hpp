#pragma once

#include <cstdint>
#include <vector>

#include <opencv2/core/mat.hpp>

#include "medicore_vision/types.hpp"

namespace medicore::vision {

cv::Mat decode_image(const std::vector<std::uint8_t>& encoded);
ImageMetadata inspect_image(const cv::Mat& image);
cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side = 2048);

}  // namespace medicore::vision
