#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "medicore_vision/types.hpp"

namespace medicore::vision {

struct OnnxClassifierContract {
    std::string tensor_contract{"xray-core-v2/nchw-f32-0-1"};
    std::int64_t channels{1};
    std::int64_t height{1024};
    std::int64_t width{1024};
    std::size_t label_count{0};
};

void validate_onnx_input_tensor(
    const XRayTensor& tensor,
    const OnnxClassifierContract& contract);

void validate_onnx_output_width(
    std::size_t output_width,
    const OnnxClassifierContract& contract);

}  // namespace medicore::vision
