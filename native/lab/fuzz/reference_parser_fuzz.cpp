#include "medicore/lab/lab_extensions.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr || size == 0 || size > 4096) {
        return 0;
    }
    const std::string text(reinterpret_cast<const char*>(data), size);
    (void)medicore::lab::parse_reference_text(text);
    return 0;
}
