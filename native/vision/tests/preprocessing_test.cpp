#include <cassert>

#include <opencv2/core.hpp>

#include "medicore_vision/preprocessing.hpp"

int main() {
    cv::Mat gradient(512, 1024, CV_8UC1);
    for (int row = 0; row < gradient.rows; ++row) {
        for (int col = 0; col < gradient.cols; ++col) {
            gradient.at<std::uint8_t>(row, col) = static_cast<std::uint8_t>(
                (255 * col) / (gradient.cols - 1));
        }
    }

    const auto metadata = medicore::vision::inspect_image(gradient);
    assert(metadata.width == 1024);
    assert(metadata.height == 512);
    assert(metadata.channels == 1);

    const auto quality = medicore::vision::assess_chest_xray_quality(gradient);
    assert(quality.dynamic_range >= 250.0);
    assert(quality.stddev_intensity > 0.0);
    assert(quality.clipped_low_fraction >= 0.0);
    assert(quality.clipped_high_fraction >= 0.0);

    const cv::Mat preprocessed =
        medicore::vision::preprocess_chest_xray(gradient, 256);
    assert(preprocessed.type() == CV_8UC1);
    assert(preprocessed.cols == 256);
    assert(preprocessed.rows == 128);

    const cv::Mat tensor =
        medicore::vision::prepare_chest_xray_tensor(gradient, 512);
    assert(tensor.type() == CV_32FC1);
    assert(tensor.cols == 512);
    assert(tensor.rows == 512);

    double min_value = 0.0;
    double max_value = 0.0;
    cv::minMaxLoc(tensor, &min_value, &max_value);
    assert(min_value >= 0.0);
    assert(max_value <= 1.0);

    return 0;
}
