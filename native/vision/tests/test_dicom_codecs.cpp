#include "medicore_vision/dicom_codecs.hpp"

#include <cassert>
#include <iostream>

using namespace medicore::vision;

int main() {
    const auto caps = dicom_codec_capabilities();
    assert(caps.rle);

    assert(dicom_transfer_syntax_decodable("1.2.840.10008.1.2"));
    assert(dicom_transfer_syntax_decodable("1.2.840.10008.1.2.1"));
    assert(dicom_transfer_syntax_decodable("1.2.840.10008.1.2.5"));

    const bool jpeg = dicom_transfer_syntax_decodable("1.2.840.10008.1.2.4.50");
    assert(jpeg == caps.jpeg);
    const bool jpegls = dicom_transfer_syntax_decodable("1.2.840.10008.1.2.4.80");
    assert(jpegls == caps.jpeg_ls);
    const bool jp2k = dicom_transfer_syntax_decodable("1.2.840.10008.1.2.4.90");
    assert(jp2k == caps.jpeg2000);

    assert(!dicom_transfer_syntax_decodable("9.9.9.9.9"));

    std::cout << "dicom codec capability tests passed\n";
    return 0;
}
