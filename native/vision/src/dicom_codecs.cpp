#include "medicore_vision/dicom_codecs.hpp"

#include <mutex>
#include <stdexcept>
#include <string>

#include <dcmtk/dcmdata/dcdatset.h>
#include <dcmtk/dcmdata/dcrledrg.h>
#include <dcmtk/dcmdata/dcxfer.h>

#ifdef MEDICORE_WITH_DCMJPEG
#include <dcmtk/dcmjpeg/djdecode.h>
#endif

#ifdef MEDICORE_WITH_DCMJPLS
#include <dcmtk/dcmjpls/djdecode.h>
#endif

namespace medicore::vision {
namespace {

std::once_flag g_codec_registration_once;

void register_codecs_once() {
    std::call_once(g_codec_registration_once, [] {
        DcmRLEDecoderRegistration::registerCodecs();
#ifdef MEDICORE_WITH_DCMJPEG
        DJDecoderRegistration::registerCodecs();
#endif
#ifdef MEDICORE_WITH_DCMJPLS
        DJLSDecoderRegistration::registerCodecs();
#endif
    });
}

bool is_uncompressed_uid(const std::string& uid) {
    return uid == "1.2.840.10008.1.2" ||
        uid == "1.2.840.10008.1.2.1" ||
        uid == "1.2.840.10008.1.2.2" ||
        uid == "1.2.840.10008.1.2.1.99";
}

bool is_rle_uid(const std::string& uid) {
    return uid == "1.2.840.10008.1.2.5";
}

bool is_jpeg_uid(const std::string& uid) {
    return uid == "1.2.840.10008.1.2.4.50" ||
        uid == "1.2.840.10008.1.2.4.51" ||
        uid == "1.2.840.10008.1.2.4.57" ||
        uid == "1.2.840.10008.1.2.4.70";
}

bool is_jpegls_uid(const std::string& uid) {
    return uid == "1.2.840.10008.1.2.4.80" || uid == "1.2.840.10008.1.2.4.81";
}

bool is_jpeg2000_uid(const std::string& uid) {
    return uid == "1.2.840.10008.1.2.4.90" || uid == "1.2.840.10008.1.2.4.91";
}

}  // namespace

DicomCodecCapabilities dicom_codec_capabilities() noexcept {
    DicomCodecCapabilities result;
#ifdef MEDICORE_WITH_DCMJPEG
    result.jpeg = true;
#endif
#ifdef MEDICORE_WITH_DCMJPLS
    result.jpeg_ls = true;
#endif
#ifdef MEDICORE_WITH_DCMJP2K
    result.jpeg2000 = true;
#endif
    return result;
}

bool dicom_transfer_syntax_decodable(const std::string& uid) noexcept {
    if (is_uncompressed_uid(uid) || is_rle_uid(uid)) return true;
    const auto caps = dicom_codec_capabilities();
    if (is_jpeg_uid(uid)) return caps.jpeg;
    if (is_jpegls_uid(uid)) return caps.jpeg_ls;
    if (is_jpeg2000_uid(uid)) return caps.jpeg2000;
    return false;
}

void ensure_uncompressed_dicom_pixel_data(
    DcmDataset& dataset,
    const std::string& transfer_syntax_uid) {
    const DcmXfer original(dataset.getOriginalXfer());
    if (!original.isEncapsulated()) {
        return;
    }
    if (!dicom_transfer_syntax_decodable(transfer_syntax_uid)) {
        throw std::runtime_error(
            "Compressed DICOM transfer syntax is not supported by this build: " +
            transfer_syntax_uid);
    }

    register_codecs_once();
    const OFCondition status = dataset.chooseRepresentation(EXS_LittleEndianExplicit, nullptr);
    if (status.bad() || !dataset.canWriteXfer(EXS_LittleEndianExplicit)) {
        throw std::runtime_error(
            std::string("DICOM decompression failed: ") + status.text());
    }
}

}  // namespace medicore::vision
