#pragma once

#include <string>

class DcmDataset;

namespace medicore::vision {

struct DicomCodecCapabilities {
    bool rle{true};
    bool jpeg{false};
    bool jpeg_ls{false};
    bool jpeg2000{false};
};

DicomCodecCapabilities dicom_codec_capabilities() noexcept;
bool dicom_transfer_syntax_decodable(const std::string& transfer_syntax_uid) noexcept;
void ensure_uncompressed_dicom_pixel_data(
    DcmDataset& dataset,
    const std::string& transfer_syntax_uid);

}  // namespace medicore::vision
