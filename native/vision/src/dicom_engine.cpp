#include "medicore_vision/dicom_engine.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <dcmtk/dcmdata/dcdeftag.h>
#include <dcmtk/dcmdata/dcfilefo.h>
#include <dcmtk/dcmdata/dcistrmb.h>
#include <dcmtk/dcmdata/dcxfer.h>

namespace medicore::vision {
namespace {

std::unique_ptr<DcmFileFormat> parse_dicom(const std::vector<std::uint8_t>& encoded) {
    if (encoded.empty()) {
        throw std::invalid_argument("DICOM content cannot be empty");
    }

    DcmInputBufferStream stream;
    stream.setBuffer(encoded.data(), static_cast<offile_off_t>(encoded.size()));
    stream.setEos();

    auto file = std::make_unique<DcmFileFormat>();
    const OFCondition status = file->read(stream);
    if (status.bad()) {
        throw std::runtime_error(std::string("DICOM parse failed: ") + status.text());
    }
    if (file->getDataset() == nullptr) {
        throw std::runtime_error("DICOM dataset is missing");
    }
    return file;
}

std::string get_string(DcmDataset& dataset, const DcmTagKey& key) {
    OFString value;
    if (dataset.findAndGetOFString(key, value).good()) {
        return std::string(value.c_str());
    }
    return {};
}

int get_required_u16(DcmDataset& dataset, const DcmTagKey& key, const char* name) {
    Uint16 value = 0;
    if (dataset.findAndGetUint16(key, value).bad()) {
        throw std::runtime_error(std::string("Required DICOM tag missing: ") + name);
    }
    return static_cast<int>(value);
}

int get_frames(DcmDataset& dataset) {
    OFString value;
    if (dataset.findAndGetOFString(DCM_NumberOfFrames, value).bad() || value.empty()) {
        return 1;
    }
    try {
        const int frames = std::stoi(value.c_str());
        if (frames < 1 || frames > 100000) {
            throw std::runtime_error("Invalid DICOM NumberOfFrames");
        }
        return frames;
    } catch (const std::exception&) {
        throw std::runtime_error("Invalid DICOM NumberOfFrames");
    }
}

DicomMetadata extract_metadata(DcmDataset& dataset) {
    DicomMetadata metadata;
    metadata.rows = get_required_u16(dataset, DCM_Rows, "Rows");
    metadata.columns = get_required_u16(dataset, DCM_Columns, "Columns");
    metadata.samples_per_pixel = get_required_u16(dataset, DCM_SamplesPerPixel, "SamplesPerPixel");
    metadata.bits_allocated = get_required_u16(dataset, DCM_BitsAllocated, "BitsAllocated");
    metadata.bits_stored = get_required_u16(dataset, DCM_BitsStored, "BitsStored");
    metadata.high_bit = get_required_u16(dataset, DCM_HighBit, "HighBit");
    metadata.pixel_representation = get_required_u16(dataset, DCM_PixelRepresentation, "PixelRepresentation");
    metadata.frames = get_frames(dataset);
    metadata.modality = get_string(dataset, DCM_Modality);
    metadata.photometric_interpretation = get_string(dataset, DCM_PhotometricInterpretation);

    if (metadata.rows <= 0 || metadata.columns <= 0) {
        throw std::runtime_error("DICOM Rows/Columns must be positive");
    }
    if (metadata.samples_per_pixel != 1) {
        throw std::runtime_error("DICOM Engine v1 supports monochrome SamplesPerPixel=1 only");
    }
    if (metadata.photometric_interpretation != "MONOCHROME1" &&
        metadata.photometric_interpretation != "MONOCHROME2") {
        throw std::runtime_error("DICOM Engine v1 supports MONOCHROME1/2 only");
    }
    if (metadata.bits_allocated != 8 && metadata.bits_allocated != 16) {
        throw std::runtime_error("DICOM Engine v1 supports BitsAllocated 8 or 16 only");
    }
    if (metadata.bits_stored < 1 || metadata.bits_stored > metadata.bits_allocated) {
        throw std::runtime_error("Invalid DICOM BitsStored");
    }
    if (metadata.high_bit < metadata.bits_stored - 1 || metadata.high_bit >= metadata.bits_allocated) {
        throw std::runtime_error("Invalid DICOM HighBit");
    }
    if (metadata.pixel_representation != 0 && metadata.pixel_representation != 1) {
        throw std::runtime_error("Invalid DICOM PixelRepresentation");
    }

    Float64 number = 0.0;
    if (dataset.findAndGetFloat64(DCM_RescaleSlope, number).good() && std::isfinite(number)) {
        metadata.rescale_slope = static_cast<double>(number);
    }
    if (dataset.findAndGetFloat64(DCM_RescaleIntercept, number).good() && std::isfinite(number)) {
        metadata.rescale_intercept = static_cast<double>(number);
    }
    if (std::abs(metadata.rescale_slope) < std::numeric_limits<double>::epsilon()) {
        throw std::runtime_error("DICOM RescaleSlope cannot be zero");
    }

    Float64 center = 0.0;
    Float64 width = 0.0;
    const bool has_center = dataset.findAndGetFloat64(DCM_WindowCenter, center, 0).good();
    const bool has_width = dataset.findAndGetFloat64(DCM_WindowWidth, width, 0).good();
    if (has_center && has_width && std::isfinite(center) && std::isfinite(width) && width >= 1.0) {
        metadata.has_window = true;
        metadata.window_center = static_cast<double>(center);
        metadata.window_width = static_cast<double>(width);
    }

    Float64 row_spacing = 0.0;
    Float64 col_spacing = 0.0;
    const bool has_row_spacing = dataset.findAndGetFloat64(DCM_PixelSpacing, row_spacing, 0).good();
    const bool has_col_spacing = dataset.findAndGetFloat64(DCM_PixelSpacing, col_spacing, 1).good();
    if (has_row_spacing && has_col_spacing &&
        std::isfinite(row_spacing) && std::isfinite(col_spacing) &&
        row_spacing > 0.0 && col_spacing > 0.0) {
        metadata.has_pixel_spacing = true;
        metadata.pixel_spacing_row_mm = static_cast<double>(row_spacing);
        metadata.pixel_spacing_col_mm = static_cast<double>(col_spacing);
    }

    const DcmXfer transfer(dataset.getOriginalXfer());
    metadata.compressed = transfer.isEncapsulated();
    if (const char* name = transfer.getXferName(); name != nullptr) {
        metadata.transfer_syntax = name;
    }
    if (const char* uid = transfer.getXferID(); uid != nullptr) {
        metadata.transfer_syntax_uid = uid;
    }

    return metadata;
}

std::int32_t decode_stored_sample(
    std::uint32_t raw,
    int bits_stored,
    int high_bit,
    int pixel_representation) {
    const int shift = high_bit + 1 - bits_stored;
    if (shift < 0 || shift > 15) {
        throw std::runtime_error("Unsupported DICOM bit alignment");
    }
    raw >>= static_cast<unsigned int>(shift);
    const std::uint32_t mask = (std::uint32_t{1} << bits_stored) - 1U;
    raw &= mask;

    if (pixel_representation == 0) {
        return static_cast<std::int32_t>(raw);
    }

    const std::uint32_t sign_bit = std::uint32_t{1} << (bits_stored - 1);
    if ((raw & sign_bit) == 0) {
        return static_cast<std::int32_t>(raw);
    }
    const std::uint32_t range = std::uint32_t{1} << bits_stored;
    return static_cast<std::int32_t>(raw) - static_cast<std::int32_t>(range);
}

std::vector<double> extract_modality_frame(
    DcmDataset& dataset,
    const DicomMetadata& metadata,
    int frame_index) {
    if (metadata.compressed) {
        throw std::runtime_error(
            "Compressed/encapsulated DICOM Pixel Data is not enabled in DICOM Engine v1");
    }
    if (frame_index < 0 || frame_index >= metadata.frames) {
        throw std::out_of_range("DICOM frame_index is outside NumberOfFrames");
    }

    const std::size_t frame_pixels =
        static_cast<std::size_t>(metadata.rows) * static_cast<std::size_t>(metadata.columns);
    const std::size_t required_pixels = frame_pixels * static_cast<std::size_t>(metadata.frames);
    const std::size_t frame_offset = frame_pixels * static_cast<std::size_t>(frame_index);

    std::vector<double> values(frame_pixels);
    if (metadata.bits_allocated == 16) {
        const Uint16* pixels = nullptr;
        unsigned long count = 0;
        if (dataset.findAndGetUint16Array(DCM_PixelData, pixels, &count).bad() || pixels == nullptr) {
            throw std::runtime_error("Unable to read native 16-bit DICOM Pixel Data");
        }
        if (static_cast<std::size_t>(count) < required_pixels) {
            throw std::runtime_error("DICOM Pixel Data is shorter than Rows*Columns*Frames");
        }
        for (std::size_t index = 0; index < frame_pixels; ++index) {
            const auto stored = decode_stored_sample(
                static_cast<std::uint32_t>(pixels[frame_offset + index]),
                metadata.bits_stored,
                metadata.high_bit,
                metadata.pixel_representation);
            values[index] = static_cast<double>(stored) * metadata.rescale_slope +
                            metadata.rescale_intercept;
        }
    } else {
        const Uint8* pixels = nullptr;
        unsigned long count = 0;
        if (dataset.findAndGetUint8Array(DCM_PixelData, pixels, &count).bad() || pixels == nullptr) {
            throw std::runtime_error("Unable to read native 8-bit DICOM Pixel Data");
        }
        if (static_cast<std::size_t>(count) < required_pixels) {
            throw std::runtime_error("DICOM Pixel Data is shorter than Rows*Columns*Frames");
        }
        for (std::size_t index = 0; index < frame_pixels; ++index) {
            const auto stored = decode_stored_sample(
                static_cast<std::uint32_t>(pixels[frame_offset + index]),
                metadata.bits_stored,
                metadata.high_bit,
                metadata.pixel_representation);
            values[index] = static_cast<double>(stored) * metadata.rescale_slope +
                            metadata.rescale_intercept;
        }
    }
    return values;
}

std::pair<double, double> robust_window(const std::vector<double>& values) {
    if (values.empty()) {
        throw std::runtime_error("Cannot window empty DICOM frame");
    }
    std::vector<double> sorted(values);
    std::sort(sorted.begin(), sorted.end());
    const std::size_t last = sorted.size() - 1;
    const std::size_t low_index = static_cast<std::size_t>(std::floor(0.005 * static_cast<double>(last)));
    const std::size_t high_index = static_cast<std::size_t>(std::ceil(0.995 * static_cast<double>(last)));
    double low = sorted[low_index];
    double high = sorted[high_index];
    if (!std::isfinite(low) || !std::isfinite(high)) {
        throw std::runtime_error("DICOM modality pixels contain non-finite values");
    }
    if (high <= low) {
        low -= 0.5;
        high += 0.5;
    }
    return {(low + high) / 2.0, std::max(1.0, high - low)};
}

std::uint8_t window_to_u8(double value, double center, double width) {
    if (!std::isfinite(value) || !std::isfinite(center) || !std::isfinite(width) || width < 1.0) {
        throw std::runtime_error("Invalid DICOM window parameters");
    }

    double normalized = 0.0;
    if (width <= 1.0) {
        normalized = value > center - 0.5 ? 1.0 : 0.0;
    } else {
        const double lower = center - 0.5 - (width - 1.0) / 2.0;
        const double upper = center - 0.5 + (width - 1.0) / 2.0;
        if (value <= lower) {
            normalized = 0.0;
        } else if (value > upper) {
            normalized = 1.0;
        } else {
            normalized = ((value - (center - 0.5)) / (width - 1.0)) + 0.5;
        }
    }
    normalized = std::clamp(normalized, 0.0, 1.0);
    return static_cast<std::uint8_t>(std::lround(normalized * 255.0));
}

}  // namespace

DicomMetadata inspect_dicom(const std::vector<std::uint8_t>& encoded) {
    auto file = parse_dicom(encoded);
    return extract_metadata(*file->getDataset());
}

DicomFrame decode_dicom_frame(
    const std::vector<std::uint8_t>& encoded,
    int frame_index,
    const DicomWindowConfig& window) {
    auto file = parse_dicom(encoded);
    DcmDataset& dataset = *file->getDataset();
    const DicomMetadata metadata = extract_metadata(dataset);
    std::vector<double> values = extract_modality_frame(dataset, metadata, frame_index);

    if (window.center.has_value() != window.width.has_value()) {
        throw std::invalid_argument("DICOM window override requires both center and width");
    }

    double center = 0.0;
    double width = 0.0;
    std::string window_source;
    if (window.center && window.width) {
        center = *window.center;
        width = *window.width;
        if (!std::isfinite(center) || !std::isfinite(width) || width < 1.0) {
            throw std::invalid_argument("DICOM window override is invalid");
        }
        window_source = "override";
    } else if (metadata.has_window) {
        center = metadata.window_center;
        width = metadata.window_width;
        window_source = "dicom";
    } else {
        const auto robust = robust_window(values);
        center = robust.first;
        width = robust.second;
        window_source = "robust";
    }

    const auto [min_it, max_it] = std::minmax_element(values.begin(), values.end());
    cv::Mat image(metadata.rows, metadata.columns, CV_8UC1);
    for (int row = 0; row < metadata.rows; ++row) {
        auto* target = image.ptr<std::uint8_t>(row);
        for (int column = 0; column < metadata.columns; ++column) {
            const std::size_t index = static_cast<std::size_t>(row) *
                                          static_cast<std::size_t>(metadata.columns) +
                                      static_cast<std::size_t>(column);
            std::uint8_t rendered = window_to_u8(values[index], center, width);
            if (metadata.photometric_interpretation == "MONOCHROME1") {
                rendered = static_cast<std::uint8_t>(255U - rendered);
            }
            target[column] = rendered;
        }
    }

    DicomFrame result;
    result.image = image;
    result.metadata = metadata;
    result.frame_index = frame_index;
    result.applied_window_center = center;
    result.applied_window_width = width;
    result.modality_min = *min_it;
    result.modality_max = *max_it;
    result.window_source = window_source;
    return result;
}

bool is_xray_dicom_modality(const std::string& modality) {
    std::string normalized = modality;
    std::transform(normalized.begin(), normalized.end(), normalized.begin(), [](unsigned char value) {
        return static_cast<char>(std::toupper(value));
    });
    return normalized == "CR" || normalized == "DX";
}

}  // namespace medicore::vision
