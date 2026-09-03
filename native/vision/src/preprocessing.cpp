#include "medicore_vision/preprocessing.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

namespace medicore::vision {
namespace {

cv::Mat to_grayscale(const cv::Mat& image) {
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
    return gray;
}

cv::Mat to_grayscale_u8(const cv::Mat& image) {
    const cv::Mat gray = to_grayscale(image);
    if (gray.depth() == CV_8U) {
        return gray;
    }

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(gray, &min_value, &max_value);

    cv::Mat gray_u8;
    if (max_value <= min_value) {
        gray.convertTo(gray_u8, CV_8U);
    } else {
        gray.convertTo(
            gray_u8,
            CV_8U,
            255.0 / (max_value - min_value),
            -255.0 * min_value / (max_value - min_value));
    }
    return gray_u8;
}

}  // namespace

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

    const cv::Mat gray_u8 = to_grayscale_u8(image);

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

ImageQualityMetrics assess_chest_xray_quality(const cv::Mat& image) {
    const cv::Mat gray_u8 = to_grayscale_u8(image);

    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(gray_u8, mean, stddev);

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(gray_u8, &min_value, &max_value);

    const double pixel_count = static_cast<double>(gray_u8.total());
    if (pixel_count <= 0.0) {
        throw std::runtime_error("image contains no pixels");
    }

    const cv::Mat low_mask = gray_u8 <= 5;
    const cv::Mat high_mask = gray_u8 >= 250;
    const double clipped_low_fraction =
        static_cast<double>(cv::countNonZero(low_mask)) / pixel_count;
    const double clipped_high_fraction =
        static_cast<double>(cv::countNonZero(high_mask)) / pixel_count;

    cv::Mat laplacian;
    cv::Laplacian(gray_u8, laplacian, CV_64F, 3);
    cv::Scalar laplacian_mean;
    cv::Scalar laplacian_stddev;
    cv::meanStdDev(laplacian, laplacian_mean, laplacian_stddev);
    const double laplacian_variance =
        laplacian_stddev[0] * laplacian_stddev[0];

    return ImageQualityMetrics{
        .dynamic_range = max_value - min_value,
        .mean_intensity = mean[0],
        .stddev_intensity = stddev[0],
        .clipped_low_fraction = clipped_low_fraction,
        .clipped_high_fraction = clipped_high_fraction,
        .laplacian_variance = laplacian_variance,
    };
}

cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side) {
    if (max_side < 256 || max_side > 4096) {
        throw std::invalid_argument("max_side must be between 256 and 4096");
    }

    const cv::Mat gray = to_grayscale(image);

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

    // Keep preprocessing conservative. Model-specific enhancement must match a
    // validated training pipeline and is intentionally not applied here.
    return normalized;
}

cv::Mat prepare_chest_xray_tensor(const cv::Mat& image, int target_size) {
    if (target_size < 224 || target_size > 2048) {
        throw std::invalid_argument("target_size must be between 224 and 2048");
    }

    const cv::Mat gray = to_grayscale(image);

    cv::Mat normalized_u8;
    cv::normalize(gray, normalized_u8, 0, 255, cv::NORM_MINMAX, CV_8U);

    const double scale = std::min(
        static_cast<double>(target_size) / static_cast<double>(normalized_u8.cols),
        static_cast<double>(target_size) / static_cast<double>(normalized_u8.rows));

    const int resized_width = std::max(
        1, static_cast<int>(std::round(static_cast<double>(normalized_u8.cols) * scale)));
    const int resized_height = std::max(
        1, static_cast<int>(std::round(static_cast<double>(normalized_u8.rows) * scale)));

    cv::Mat resized;
    cv::resize(
        normalized_u8,
        resized,
        cv::Size(resized_width, resized_height),
        0.0,
        0.0,
        scale < 1.0 ? cv::INTER_AREA : cv::INTER_LINEAR);

    cv::Mat resized_float;
    resized.convertTo(resized_float, CV_32F, 1.0 / 255.0);

    cv::Mat tensor = cv::Mat::zeros(target_size, target_size, CV_32FC1);
    const int offset_x = (target_size - resized_width) / 2;
    const int offset_y = (target_size - resized_height) / 2;
    resized_float.copyTo(
        tensor(cv::Rect(offset_x, offset_y, resized_width, resized_height)));

    return tensor;
}

}  // namespace medicore::vision
