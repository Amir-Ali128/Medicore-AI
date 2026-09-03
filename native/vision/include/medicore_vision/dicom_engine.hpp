#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include <opencv2/core/mat.hpp>

namespace medicore::vision {

inline constexpr const char* kDicomFrameContract = "dicom-frame-v1/grayscale-u8";

struct DicomMetadata {
    int rows{0};
    int columns{0};
    int frames{1};
    int samples_per_pixel{0};
    int bits_allocated{0};
    int bits_stored{0};
    int high_bit{0};
    int pixel_representation{0};
    std::string modality{};
    std::string photometric_interpretation{};
    std::string transfer_syntax{};
    std::string transfer_syntax_uid{};
    bool compressed{false};
    double rescale_slope{1.0};
    double rescale_intercept{0.0};
    bool has_window{false};
    double window_center{0.0};
    double window_width{0.0};
};

struct DicomWindowConfig {
    std::optional<double> center{};
    std::optional<double> width{};
};

struct DicomFrame {
    cv::Mat image{};
    DicomMetadata metadata{};
    int frame_index{0};
    double applied_window_center{0.0};
    double applied_window_width{0.0};
    double modality_min{0.0};
    double modality_max{0.0};
    std::string window_source{};
    std::string contract_version{kDicomFrameContract};
};

DicomMetadata inspect_dicom(const std::vector<std::uint8_t>& encoded);

DicomFrame decode_dicom_frame(
    const std::vector<std::uint8_t>& encoded,
    int frame_index = 0,
    const DicomWindowConfig& window = DicomWindowConfig{});

bool is_xray_dicom_modality(const std::string& modality);

}  // namespace medicore::vision
