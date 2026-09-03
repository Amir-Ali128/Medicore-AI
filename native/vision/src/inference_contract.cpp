#include "medicore_vision/inference_contract.hpp"

#include <limits>
#include <stdexcept>

namespace medicore::vision {

void validate_onnx_input_tensor(
    const XRayTensor& tensor,
    const OnnxClassifierContract& contract) {
    if (contract.tensor_contract.empty()) {
        throw std::invalid_argument("ONNX tensor contract cannot be empty");
    }
    if (tensor.contract_version != contract.tensor_contract) {
        throw std::invalid_argument("X-Ray tensor contract mismatch");
    }
    if (contract.channels != 1 || contract.height <= 0 || contract.width <= 0) {
        throw std::invalid_argument("invalid ONNX classifier input contract");
    }
    if (tensor.shape[0] != 1 ||
        tensor.shape[1] != contract.channels ||
        tensor.shape[2] != contract.height ||
        tensor.shape[3] != contract.width) {
        throw std::invalid_argument("X-Ray tensor shape mismatch");
    }

    const auto height = static_cast<std::size_t>(contract.height);
    const auto width = static_cast<std::size_t>(contract.width);
    if (height > std::numeric_limits<std::size_t>::max() / width) {
        throw std::overflow_error("ONNX tensor size overflow");
    }
    const auto expected_values = height * width;
    if (tensor.values.size() != expected_values) {
        throw std::invalid_argument("X-Ray tensor value count mismatch");
    }
    for (const float value : tensor.values) {
        if (!(value >= 0.0F && value <= 1.0F)) {
            throw std::invalid_argument("X-Ray tensor value outside [0,1]");
        }
    }
}

void validate_onnx_output_width(
    const std::size_t output_width,
    const OnnxClassifierContract& contract) {
    if (contract.label_count == 0) {
        throw std::invalid_argument("ONNX classifier label_count cannot be zero");
    }
    if (output_width != contract.label_count) {
        throw std::invalid_argument("ONNX classifier output width mismatch");
    }
}

}  // namespace medicore::vision
