#include "medicore_vision/postprocessing.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

#include <opencv2/imgproc.hpp>

namespace medicore::vision {
namespace {

void validate_config(const SpatialPostprocessConfig& config) {
    if (!std::isfinite(config.threshold) || config.threshold < 0.0 || config.threshold > 1.0) {
        throw std::invalid_argument("postprocess threshold must be within [0,1]");
    }
    if (config.min_component_area < 1) {
        throw std::invalid_argument("min_component_area must be positive");
    }
    if (config.max_components < 1 || config.max_components > 1024) {
        throw std::invalid_argument("max_components must be between 1 and 1024");
    }
    if (config.pixel_spacing_row_mm.has_value() != config.pixel_spacing_col_mm.has_value()) {
        throw std::invalid_argument("pixel spacing requires both row and column values");
    }
    if (config.pixel_spacing_row_mm) {
        if (!std::isfinite(*config.pixel_spacing_row_mm) ||
            !std::isfinite(*config.pixel_spacing_col_mm) ||
            *config.pixel_spacing_row_mm <= 0.0 ||
            *config.pixel_spacing_col_mm <= 0.0) {
            throw std::invalid_argument("pixel spacing values must be finite and positive");
        }
    }
}

cv::Mat normalize_spatial_map(const cv::Mat& spatial_map, bool normalize_minmax) {
    if (spatial_map.empty() || spatial_map.dims != 2 || spatial_map.channels() != 1) {
        throw std::invalid_argument("spatial map must be a non-empty 2D single-channel matrix");
    }

    cv::Mat float_map;
    spatial_map.convertTo(float_map, CV_32FC1);

    double minimum = std::numeric_limits<double>::infinity();
    double maximum = -std::numeric_limits<double>::infinity();
    for (int row = 0; row < float_map.rows; ++row) {
        const float* source = float_map.ptr<float>(row);
        for (int column = 0; column < float_map.cols; ++column) {
            const double value = static_cast<double>(source[column]);
            if (!std::isfinite(value)) {
                throw std::invalid_argument("spatial map cannot contain NaN/Inf");
            }
            minimum = std::min(minimum, value);
            maximum = std::max(maximum, value);
        }
    }

    if (normalize_minmax) {
        const double range = maximum - minimum;
        if (range <= std::numeric_limits<double>::epsilon()) {
            return cv::Mat::zeros(float_map.size(), CV_32FC1);
        }
        float_map = (float_map - static_cast<float>(minimum)) / static_cast<float>(range);
        return float_map;
    }

    if (minimum < -1e-6 || maximum > 1.0 + 1e-6) {
        throw std::invalid_argument(
            "spatial map values must be within [0,1] when min-max normalization is disabled");
    }
    for (int row = 0; row < float_map.rows; ++row) {
        float* target = float_map.ptr<float>(row);
        for (int column = 0; column < float_map.cols; ++column) {
            target[column] = std::clamp(target[column], 0.0F, 1.0F);
        }
    }
    return float_map;
}

cv::Mat map_heatmap_to_original(
    const cv::Mat& normalized_map,
    const TensorTransform& transform) {
    cv::Mat tensor_space;
    if (normalized_map.cols == transform.output_width &&
        normalized_map.rows == transform.output_height) {
        tensor_space = normalized_map;
    } else {
        cv::resize(
            normalized_map,
            tensor_space,
            cv::Size(transform.output_width, transform.output_height),
            0.0,
            0.0,
            cv::INTER_LINEAR);
    }

    const cv::Rect content_roi(
        transform.pad_left,
        transform.pad_top,
        transform.resized_width,
        transform.resized_height);
    if (content_roi.x < 0 || content_roi.y < 0 ||
        content_roi.x + content_roi.width > tensor_space.cols ||
        content_roi.y + content_roi.height > tensor_space.rows) {
        throw std::invalid_argument("tensor transform content ROI is outside model space");
    }

    const cv::Mat content = tensor_space(content_roi);
    cv::Mat original_space;
    cv::resize(
        content,
        original_space,
        cv::Size(transform.original_width, transform.original_height),
        0.0,
        0.0,
        cv::INTER_LINEAR);
    return original_space;
}

std::vector<RegionMeasurement> measure_regions(
    const cv::Mat& heatmap,
    const cv::Mat& mask,
    const SpatialPostprocessConfig& config) {
    cv::Mat labels;
    cv::Mat stats;
    cv::Mat centroids;
    const int component_count = cv::connectedComponentsWithStats(
        mask,
        labels,
        stats,
        centroids,
        8,
        CV_32S);

    std::vector<RegionMeasurement> regions;
    regions.reserve(static_cast<std::size_t>(std::max(0, component_count - 1)));
    const double image_area =
        static_cast<double>(heatmap.rows) * static_cast<double>(heatmap.cols);

    for (int component = 1; component < component_count; ++component) {
        const int area = stats.at<int>(component, cv::CC_STAT_AREA);
        if (area < config.min_component_area) {
            continue;
        }

        RegionMeasurement region;
        region.component_id = component;
        region.x = stats.at<int>(component, cv::CC_STAT_LEFT);
        region.y = stats.at<int>(component, cv::CC_STAT_TOP);
        region.width = stats.at<int>(component, cv::CC_STAT_WIDTH);
        region.height = stats.at<int>(component, cv::CC_STAT_HEIGHT);
        region.area_pixels = area;
        region.area_fraction = static_cast<double>(area) / image_area;
        region.centroid_x = centroids.at<double>(component, 0);
        region.centroid_y = centroids.at<double>(component, 1);

        double score_sum = 0.0;
        double peak = 0.0;
        for (int row = region.y; row < region.y + region.height; ++row) {
            const int* label_row = labels.ptr<int>(row);
            const float* heat_row = heatmap.ptr<float>(row);
            for (int column = region.x; column < region.x + region.width; ++column) {
                if (label_row[column] != component) {
                    continue;
                }
                const double score = static_cast<double>(heat_row[column]);
                score_sum += score;
                peak = std::max(peak, score);
            }
        }
        region.mean_score = score_sum / static_cast<double>(area);
        region.peak_score = peak;

        if (config.pixel_spacing_row_mm && config.pixel_spacing_col_mm) {
            const double row_spacing = *config.pixel_spacing_row_mm;
            const double col_spacing = *config.pixel_spacing_col_mm;
            region.area_mm2 = static_cast<double>(area) * row_spacing * col_spacing;
            region.bbox_width_mm = static_cast<double>(region.width) * col_spacing;
            region.bbox_height_mm = static_cast<double>(region.height) * row_spacing;
        }
        regions.push_back(region);
    }

    std::sort(regions.begin(), regions.end(), [](const RegionMeasurement& left, const RegionMeasurement& right) {
        if (left.peak_score != right.peak_score) {
            return left.peak_score > right.peak_score;
        }
        if (left.mean_score != right.mean_score) {
            return left.mean_score > right.mean_score;
        }
        return left.area_pixels > right.area_pixels;
    });

    if (regions.size() > static_cast<std::size_t>(config.max_components)) {
        regions.resize(static_cast<std::size_t>(config.max_components));
    }
    return regions;
}

}  // namespace

void validate_tensor_transform(const TensorTransform& transform) {
    if (transform.original_width <= 0 || transform.original_height <= 0 ||
        transform.output_width <= 0 || transform.output_height <= 0 ||
        transform.resized_width <= 0 || transform.resized_height <= 0) {
        throw std::invalid_argument("tensor transform dimensions must be positive");
    }
    if (transform.pad_left < 0 || transform.pad_top < 0 ||
        transform.pad_right < 0 || transform.pad_bottom < 0) {
        throw std::invalid_argument("tensor transform padding cannot be negative");
    }
    if (transform.pad_left + transform.resized_width + transform.pad_right !=
            transform.output_width ||
        transform.pad_top + transform.resized_height + transform.pad_bottom !=
            transform.output_height) {
        throw std::invalid_argument("tensor transform resize/padding geometry is inconsistent");
    }
    if (!std::isfinite(transform.scale_x) || !std::isfinite(transform.scale_y) ||
        transform.scale_x <= 0.0 || transform.scale_y <= 0.0) {
        throw std::invalid_argument("tensor transform scale must be finite and positive");
    }
}

BoxF map_model_box_to_original(
    const BoxF& model_box,
    const TensorTransform& transform,
    bool clip) {
    validate_tensor_transform(transform);
    if (!std::isfinite(model_box.x1) || !std::isfinite(model_box.y1) ||
        !std::isfinite(model_box.x2) || !std::isfinite(model_box.y2) ||
        model_box.x2 <= model_box.x1 || model_box.y2 <= model_box.y1) {
        throw std::invalid_argument("model box must be finite and non-degenerate");
    }

    double x1 = model_box.x1;
    double y1 = model_box.y1;
    double x2 = model_box.x2;
    double y2 = model_box.y2;

    if (clip) {
        const double content_x1 = static_cast<double>(transform.pad_left);
        const double content_y1 = static_cast<double>(transform.pad_top);
        const double content_x2 = static_cast<double>(transform.pad_left + transform.resized_width);
        const double content_y2 = static_cast<double>(transform.pad_top + transform.resized_height);
        x1 = std::clamp(x1, content_x1, content_x2);
        x2 = std::clamp(x2, content_x1, content_x2);
        y1 = std::clamp(y1, content_y1, content_y2);
        y2 = std::clamp(y2, content_y1, content_y2);
        if (x2 <= x1 || y2 <= y1) {
            throw std::invalid_argument("model box falls entirely inside letterbox padding");
        }
    }

    BoxF original{
        .x1 = (x1 - static_cast<double>(transform.pad_left)) / transform.scale_x,
        .y1 = (y1 - static_cast<double>(transform.pad_top)) / transform.scale_y,
        .x2 = (x2 - static_cast<double>(transform.pad_left)) / transform.scale_x,
        .y2 = (y2 - static_cast<double>(transform.pad_top)) / transform.scale_y,
    };

    if (clip) {
        original.x1 = std::clamp(original.x1, 0.0, static_cast<double>(transform.original_width));
        original.x2 = std::clamp(original.x2, 0.0, static_cast<double>(transform.original_width));
        original.y1 = std::clamp(original.y1, 0.0, static_cast<double>(transform.original_height));
        original.y2 = std::clamp(original.y2, 0.0, static_cast<double>(transform.original_height));
    }
    if (original.x2 <= original.x1 || original.y2 <= original.y1) {
        throw std::invalid_argument("mapped original-space box is degenerate");
    }
    return original;
}

SpatialPostprocessResult postprocess_spatial_map(
    const cv::Mat& spatial_map,
    const TensorTransform& transform,
    const SpatialPostprocessConfig& config) {
    validate_tensor_transform(transform);
    validate_config(config);

    const cv::Mat normalized = normalize_spatial_map(spatial_map, config.normalize_minmax);
    cv::Mat original_heatmap = map_heatmap_to_original(normalized, transform);

    cv::Mat mask;
    cv::compare(original_heatmap, config.threshold, mask, cv::CMP_GE);

    SpatialPostprocessResult result;
    result.heatmap_original = original_heatmap;
    result.mask_original = mask;
    result.regions = measure_regions(original_heatmap, mask, config);
    return result;
}

}  // namespace medicore::vision
