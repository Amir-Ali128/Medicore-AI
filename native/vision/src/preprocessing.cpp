#include "medicore_vision/preprocessing.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

namespace medicore::vision {

cv::Mat decode_image(const std::vector<std::uint8_t>& encoded) {
    if (encoded.empty()) {
        throw std::invalid_argument("encoded image is empty");
    }

    cv::Mat buffer(1, static_cast<int>(encoded.size()), CV_8U,
                   const_cast<std::uint8_t*>(encoded.data()));
    cv::Mat image = cv::imdecode(buffer, cv::IMREAD_UNCHANGED);
    if (image.empty()) {
        throw std::runtime_error("image decode failed");
    }
    return image;
}

ImageMetadata inspect_image(const cv::Mat& image) {
    if (image.empty()) {
        throw std::invalid_argument("image is empty");
    }

    cv::Mat gray;
    if (image.channels() == 1) {
        gray = image;
    } else if (image.channels() == 3) {
        cv::cvtColor(image, gray, cv::COLOR_BGR2GRAY);
    } else if (image.channels() == 4) {
        cv::cvtColor(image, gray, cv::COLOR_BGRA2GRAY);
    } else {
        throw std::runtime_error("unsupported channel count");
    }

    cv::Mat gray_u8;
    if (gray.depth() == CV_8U) {
        gray_u8 = gray;
    } else {
        double min_value = 0.0;
        double max_value = 0.0;
        cv::minMaxLoc(gray, &min_value, &max_value);
        if (max_value <= min_value) {
            gray.convertTo(gray_u8, CV_8U);
        } else {
            gray.convertTo(
                gray_u8,
                CV_8U,
                255.0 / (max_value - min_value),
                -255.0 * min_value / (max_value - min_value));
        }
    }

    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(gray_u8, mean, stddev);

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(gray_u8, &min_value, &max_value);

    return ImageMetadata{
        .width = image.cols,
        .height = image.rows,
        .channels = image.channels(),
        .mean_intensity = mean[0],
        .stddev_intensity = stddev[0],
        .min_intensity = static_cast<std::uint8_t>(std::clamp(min_value, 0.0, 255.0)),
        .max_intensity = static_cast<std::uint8_t>(std::clamp(max_value, 0.0, 255.0)),
    };
}

cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side) {
    if (image.empty()) {
        throw std::invalid_argument("image is empty");
    }
    if (max_side < 256 || max_side > 4096) {
        throw std::invalid_argument("max_side must be between 256 and 4096");
    }

    cv::Mat gray;
    if (image.channels() == 1) {
        gray = image;
    } else if (image.channels() == 3) {
        cv::cvtColor(image, gray, cv::COLOR_BGR2GRAY);
    } else if (image.channels() == 4) {
        cv::cvtColor(image, gray, cv::COLOR_BGRA2GRAY);
    } else {
        throw std::runtime_error("unsupported channel count");
    }

    cv::Mat normalized;
    cv::normalize(gray, normalized, 0, 255, cv::NORM_MINMAX, CV_8U);

    const int longest_side = std::max(normalized.cols, normalized.rows);
    if (longest_side > max_side) {
        const double scale = static_cast<double>(max_side) /
                             static_cast<double>(longest_side);
        cv::resize(
            normalized,
            normalized,
            cv::Size(),
            scale,
            scale,
            cv::INTER_AREA);
    }

    // Keep preprocessing conservative. Clinical enhancement (CLAHE/windowing)
    // should be enabled only when validated against the target model's training
    // pipeline; this foundation intentionally avoids inventing image detail.
    return normalized;
}

}  // namespace medicore::vision
