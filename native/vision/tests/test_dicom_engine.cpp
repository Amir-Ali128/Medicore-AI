#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <dcmtk/dcmdata/dctk.h>

#include "medicore_vision/dicom_engine.hpp"
#include "medicore_vision/preprocessing.hpp"

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open generated DICOM");
    }
    return std::vector<std::uint8_t>(
        std::istreambuf_iterator<char>(input),
        std::istreambuf_iterator<char>());
}

std::vector<std::uint8_t> build_dicom(
    const std::string& modality,
    const std::string& photometric,
    int rows,
    int columns,
    int frames,
    int bits_stored,
    int high_bit,
    int pixel_representation,
    const std::vector<Uint16>& pixels,
    bool include_window,
    double window_center = 0.0,
    double window_width = 0.0,
    double slope = 1.0,
    double intercept = 0.0) {
    static int counter = 1;
    DcmFileFormat file;
    DcmDataset* dataset = file.getDataset();
    const std::string instance_uid =
        "1.2.826.0.1.3680043.10.543.100." + std::to_string(counter++);

    dataset->putAndInsertString(
        DCM_SOPClassUID,
        modality == "CT" ? "1.2.840.10008.5.1.4.1.1.2" : "1.2.840.10008.5.1.4.1.1.1.1");
    dataset->putAndInsertString(DCM_SOPInstanceUID, instance_uid.c_str());
    dataset->putAndInsertString(DCM_Modality, modality.c_str());
    dataset->putAndInsertUint16(DCM_Rows, static_cast<Uint16>(rows));
    dataset->putAndInsertUint16(DCM_Columns, static_cast<Uint16>(columns));
    dataset->putAndInsertUint16(DCM_SamplesPerPixel, 1);
    dataset->putAndInsertString(DCM_PhotometricInterpretation, photometric.c_str());
    dataset->putAndInsertUint16(DCM_BitsAllocated, 16);
    dataset->putAndInsertUint16(DCM_BitsStored, static_cast<Uint16>(bits_stored));
    dataset->putAndInsertUint16(DCM_HighBit, static_cast<Uint16>(high_bit));
    dataset->putAndInsertUint16(
        DCM_PixelRepresentation,
        static_cast<Uint16>(pixel_representation));
    if (frames > 1) {
        dataset->putAndInsertString(DCM_NumberOfFrames, std::to_string(frames).c_str());
    }
    dataset->putAndInsertString(DCM_RescaleSlope, std::to_string(slope).c_str());
    dataset->putAndInsertString(DCM_RescaleIntercept, std::to_string(intercept).c_str());
    if (include_window) {
        dataset->putAndInsertString(DCM_WindowCenter, std::to_string(window_center).c_str());
        dataset->putAndInsertString(DCM_WindowWidth, std::to_string(window_width).c_str());
    }
    dataset->putAndInsertUint16Array(
        DCM_PixelData,
        pixels.data(),
        static_cast<unsigned long>(pixels.size()));

    const auto path = std::filesystem::temp_directory_path() /
                      ("medicore_dicom_test_" + std::to_string(counter) + ".dcm");
    const OFCondition status = file.saveFile(path.string().c_str(), EXS_LittleEndianExplicit);
    if (status.bad()) {
        throw std::runtime_error(std::string("failed to write synthetic DICOM: ") + status.text());
    }
    auto bytes = read_bytes(path);
    std::filesystem::remove(path);
    return bytes;
}

void test_metadata_and_dicom_window() {
    const auto bytes = build_dicom(
        "DX",
        "MONOCHROME2",
        2,
        3,
        1,
        12,
        11,
        0,
        {0, 500, 1000, 1500, 2000, 2500},
        true,
        1000.0,
        2000.0);

    const auto metadata = medicore::vision::inspect_dicom(bytes);
    require(metadata.rows == 2 && metadata.columns == 3, "DICOM dimensions mismatch");
    require(metadata.frames == 1, "DICOM frame count mismatch");
    require(metadata.modality == "DX", "DICOM modality mismatch");
    require(metadata.photometric_interpretation == "MONOCHROME2", "photometric mismatch");
    require(metadata.bits_allocated == 16 && metadata.bits_stored == 12, "bit depth mismatch");
    require(metadata.has_window, "DICOM window should be detected");
    require(!metadata.compressed, "explicit little endian should not be compressed");

    const auto frame = medicore::vision::decode_dicom_frame(bytes);
    require(frame.image.rows == 2 && frame.image.cols == 3, "decoded frame shape mismatch");
    require(frame.image.type() == CV_8UC1, "decoded frame must be uint8 grayscale");
    require(frame.window_source == "dicom", "DICOM window should be preferred");
    require(frame.image.at<std::uint8_t>(0, 0) < frame.image.at<std::uint8_t>(0, 2),
            "windowed intensities should be monotonic");
    require(frame.image.at<std::uint8_t>(0, 2) < frame.image.at<std::uint8_t>(1, 2),
            "high pixels should remain brighter in MONOCHROME2");

    const auto tensor = medicore::vision::prepare_xray_tensor(
        frame.image,
        medicore::vision::XRayPreprocessConfig{
            .target_width = 64,
            .target_height = 64,
            .preserve_aspect_ratio = true,
            .pad_value = 0,
        });
    require(tensor.shape[0] == 1 && tensor.shape[1] == 1 && tensor.shape[2] == 64 &&
                tensor.shape[3] == 64,
            "DICOM-to-XRay tensor shape mismatch");
    require(tensor.contract_version == "xray-core-v2/nchw-f32-0-1", "tensor contract mismatch");
}

void test_monochrome1_inversion_and_robust_window() {
    const auto bytes = build_dicom(
        "CR",
        "MONOCHROME1",
        1,
        4,
        1,
        12,
        11,
        0,
        {0, 1000, 2000, 3000},
        false);

    const auto frame = medicore::vision::decode_dicom_frame(bytes);
    require(frame.window_source == "robust", "missing DICOM window should use robust fallback");
    require(frame.image.at<std::uint8_t>(0, 0) > frame.image.at<std::uint8_t>(0, 3),
            "MONOCHROME1 must invert display polarity");
}

void test_signed_multiframe_and_override_window() {
    std::vector<Uint16> pixels;
    for (const std::int16_t value : {-1000, -500, 0, 500, 1000, 1500, 2000, 2500}) {
        pixels.push_back(static_cast<Uint16>(value));
    }
    const auto bytes = build_dicom(
        "CT",
        "MONOCHROME2",
        2,
        2,
        2,
        16,
        15,
        1,
        pixels,
        false);

    medicore::vision::DicomWindowConfig window;
    window.center = 1750.0;
    window.width = 2000.0;
    const auto frame = medicore::vision::decode_dicom_frame(bytes, 1, window);
    require(frame.frame_index == 1, "requested multi-frame index not preserved");
    require(frame.window_source == "override", "explicit window should win");
    require(frame.modality_min == 1000.0 && frame.modality_max == 2500.0,
            "signed multi-frame extraction selected wrong pixels");
    require(!medicore::vision::is_xray_dicom_modality(frame.metadata.modality),
            "CT must not be accepted as X-Ray classifier modality");

    bool threw = false;
    try {
        (void)medicore::vision::decode_dicom_frame(bytes, 2, window);
    } catch (const std::out_of_range&) {
        threw = true;
    }
    require(threw, "out-of-range frame index must fail closed");
}

}  // namespace

int main() {
    try {
        test_metadata_and_dicom_window();
        test_monochrome1_inversion_and_robust_window();
        test_signed_multiframe_and_override_window();
        std::cout << "DICOM Engine tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "DICOM Engine test failure: " << error.what() << '\n';
        return 1;
    }
}
