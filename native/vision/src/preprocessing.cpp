#include "medicore_vision/preprocessing.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <numeric>
#include <stdexcept>

#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

namespace medicore::vision {
namespace {

std::array<std::uint64_t, 256> histogram_u8(const cv::Mat& gray) {
    if (gray.empty() || gray.type() != CV_8UC1) {
        throw std::invalid_argument("histogram expects CV_8UC1 image");
    }
    std::array<std::uint64_t, 256> histogram{};
    for (int row = 0; row < gray.rows; ++row) {
        const auto* pixels = gray.ptr<std::uint8_t>(row);
        for (int col = 0; col < gray.cols; ++col) {
            ++histogram[pixels[col]];
        }
    }
    return histogram;
}

int percentile_from_histogram(
    const std::array<std::uint64_t, 256>& histogram,
    double quantile) {
    const auto total = std::accumulate(
        histogram.begin(), histogram.end(), std::uint64_t{0});
    if (total == 0) {
        return 0;
    }
    const auto rank = static_cast<std::uint64_t>(
        std::floor(std::clamp(quantile, 0.0, 1.0) * static_cast<double>(total - 1)));
    std::uint64_t cumulative = 0;
    for (int value = 0; value < 256; ++value) {
        cumulative += histogram[static_cast<std::size_t>(value)];
        if (cumulative > rank) {
            return value;
        }
    }
    return 255;
}

void validate_tensor_config(const XRayPreprocessConfig& config) {
    if (config.target_width < 32 || config.target_width > 4096 ||
        config.target_height < 32 || config.target_height > 4096) {
        throw std::invalid_argument("target dimensions must be between 32 and 4096");
    }
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

cv::Mat to_grayscale_u8(const cv::Mat& image) {
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

    if (gray.depth() == CV_8U) {
        return gray.clone();
    }

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(gray, &min_value, &max_value);
    if (!std::isfinite(min_value) || !std::isfinite(max_value)) {
        throw std::runtime_error("image contains non-finite intensity range");
    }
    if (max_value <= min_value) {
        return cv::Mat::zeros(gray.size(), CV_8UC1);
    }

    cv::Mat result;
    gray.convertTo(
        result,
        CV_8U,
        255.0 / (max_value - min_value),
        -255.0 * min_value / (max_value - min_value));
    return result;
}

ImageMetadata inspect_image(const cv::Mat& image) {
    const cv::Mat gray = to_grayscale_u8(image);

    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(gray, mean, stddev);

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(gray, &min_value, &max_value);

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

XRayQualityMetrics inspect_xray_quality(const cv::Mat& image) {
    const cv::Mat gray = to_grayscale_u8(image);
    const auto histogram = histogram_u8(gray);
    const auto total = static_cast<double>(gray.total());

    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(gray, mean, stddev);

    const int p01 = percentile_from_histogram(histogram, 0.01);
    const int p99 = percentile_from_histogram(histogram, 0.99);
    const double robust_range = static_cast<double>(std::max(0, p99 - p01)) / 255.0;

    const std::uint64_t low_count = histogram[0] + histogram[1];
    const std::uint64_t high_count = histogram[254] + histogram[255];

    double entropy = 0.0;
    for (const auto count : histogram) {
        if (count == 0) {
            continue;
        }
        const double probability = static_cast<double>(count) / total;
        entropy -= probability * std::log2(probability);
    }

    cv::Mat laplacian;
    cv::Laplacian(gray, laplacian, CV_64F, 3);
    cv::Scalar lap_mean;
    cv::Scalar lap_stddev;
    cv::meanStdDev(laplacian, lap_mean, lap_stddev);
    const double laplacian_variance =
        (lap_stddev[0] * lap_stddev[0]) / (255.0 * 255.0);

    std::vector<std::string> flags;
    const double normalized_stddev = stddev[0] / 255.0;
    const double low_clip_ratio = static_cast<double>(low_count) / total;
    const double high_clip_ratio = static_cast<double>(high_count) / total;

    // These are technical screening heuristics, not diagnostic quality thresholds.
    if (image.cols < 256 || image.rows < 256) {
        flags.emplace_back("SMALL_IMAGE");
    }
    if (robust_range < 0.12) {
        flags.emplace_back("LOW_CONTRAST");
    }
    if (normalized_stddev < 0.02) {
        flags.emplace_back("NEAR_UNIFORM");
    }
    if (low_clip_ratio > 0.25) {
        flags.emplace_back("HEAVY_BLACK_CLIPPING");
    }
    if (high_clip_ratio > 0.25) {
        flags.emplace_back("HEAVY_WHITE_CLIPPING");
    }
    if (laplacian_variance < 0.0005) {
        flags.emplace_back("LOW_SHARPNESS_HEURISTIC");
    }

    return XRayQualityMetrics{
        .width = image.cols,
        .height = image.rows,
        .mean_intensity = mean[0] / 255.0,
        .stddev_intensity = normalized_stddev,
        .p01_intensity = static_cast<double>(p01) / 255.0,
        .p99_intensity = static_cast<double>(p99) / 255.0,
        .robust_dynamic_range = robust_range,
        .low_clip_ratio = low_clip_ratio,
        .high_clip_ratio = high_clip_ratio,
        .entropy_bits = entropy,
        .laplacian_variance = laplacian_variance,
        .technical_flags = std::move(flags),
    };
}

cv::Mat robust_normalize_xray(const cv::Mat& image) {
    const cv::Mat gray = to_grayscale_u8(image);
    const auto histogram = histogram_u8(gray);
    const int low = percentile_from_histogram(histogram, 0.005);
    const int high = percentile_from_histogram(histogram, 0.995);

    if (high <= low) {
        return cv::Mat::zeros(gray.size(), CV_8UC1);
    }

    cv::Mat floating;
    gray.convertTo(floating, CV_32F);
    floating = (floating - static_cast<float>(low)) /
               static_cast<float>(high - low);
    cv::max(floating, 0.0, floating);
    cv::min(floating, 1.0, floating);

    cv::Mat normalized;
    floating.convertTo(normalized, CV_8U, 255.0);
    return normalized;
}

XRayTensor prepare_xray_tensor(
    const cv::Mat& image,
    const XRayPreprocessConfig& config) {
    if (image.empty()) {
        throw std::invalid_argument("image is empty");
    }
    validate_tensor_config(config);

    const XRayQualityMetrics quality = inspect_xray_quality(image);
    const cv::Mat normalized = robust_normalize_xray(image);

    TensorTransform transform{
        .original_width = normalized.cols,
        .original_height = normalized.rows,
        .output_width = config.target_width,
        .output_height = config.target_height,
    };

    cv::Mat output;
    if (config.preserve_aspect_ratio) {
        const double scale = std::min(
            static_cast<double>(config.target_width) / normalized.cols,
            static_cast<double>(config.target_height) / normalized.rows);
        const int resized_width = std::max(1, static_cast<int>(std::lround(normalized.cols * scale)));
        const int resized_height = std::max(1, static_cast<int>(std::lround(normalized.rows * scale)));

        cv::Mat resized;
        cv::resize(
            normalized,
            resized,
            cv::Size(resized_width, resized_height),
            0.0,
            0.0,
            scale < 1.0 ? cv::INTER_AREA : cv::INTER_LINEAR);

        const int pad_left = (config.target_width - resized_width) / 2;
        const int pad_right = config.target_width - resized_width - pad_left;
        const int pad_top = (config.target_height - resized_height) / 2;
        const int pad_bottom = config.target_height - resized_height - pad_top;
        cv::copyMakeBorder(
            resized,
            output,
            pad_top,
            pad_bottom,
            pad_left,
            pad_right,
            cv::BORDER_CONSTANT,
            cv::Scalar(config.pad_value));

        transform.resized_width = resized_width;
        transform.resized_height = resized_height;
        transform.pad_left = pad_left;
        transform.pad_top = pad_top;
        transform.pad_right = pad_right;
        transform.pad_bottom = pad_bottom;
        transform.scale_x = static_cast<double>(resized_width) / normalized.cols;
        transform.scale_y = static_cast<double>(resized_height) / normalized.rows;
    } else {
        cv::resize(
            normalized,
            output,
            cv::Size(config.target_width, config.target_height),
            0.0,
            0.0,
            (config.target_width < normalized.cols || config.target_height < normalized.rows)
                ? cv::INTER_AREA
                : cv::INTER_LINEAR);
        transform.resized_width = config.target_width;
        transform.resized_height = config.target_height;
        transform.scale_x = static_cast<double>(config.target_width) / normalized.cols;
        transform.scale_y = static_cast<double>(config.target_height) / normalized.rows;
    }

    cv::Mat tensor_image;
    output.convertTo(tensor_image, CV_32F, 1.0 / 255.0);
    if (!tensor_image.isContinuous()) {
        tensor_image = tensor_image.clone();
    }

    const auto count = static_cast<std::size_t>(tensor_image.total());
    const auto* begin = tensor_image.ptr<float>(0);
    std::vector<float> values(begin, begin + count);

    return XRayTensor{
        .values = std::move(values),
        .shape = {1, 1, config.target_height, config.target_width},
        .transform = transform,
        .quality = quality,
        .contract_version = "xray-core-v2/nchw-f32-0-1",
    };
}

cv::Mat preprocess_chest_xray(const cv::Mat& image, int max_side) {
    if (image.empty()) {
        throw std::invalid_argument("image is empty");
    }
    if (max_side < 256 || max_side > 4096) {
        throw std::invalid_argument("max_side must be between 256 and 4096");
    }

    cv::Mat normalized = robust_normalize_xray(image);
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
    return normalized;
}

}  // namespace medicore::vision
