#include "medicore_vision/dicom_engine.hpp"

#include <cstddef>
#include <cstdint>
#include <vector>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr || size == 0 || size > 4 * 1024 * 1024) {
        return 0;
    }
    try {
        const std::vector<std::uint8_t> bytes(data, data + size);
        (void)medicore::vision::inspect_dicom(bytes);
    } catch (...) {
        // Invalid DICOM is an expected fuzz outcome. Sanitizers detect memory/UB faults.
    }
    return 0;
}
