#include <cassert>
#include <stdexcept>
#include <string>
#include <vector>

#include "medicore_vision/inference_contract.hpp"

namespace {

template <typename Function>
bool throws_invalid_argument(Function&& function) {
    try {
        function();
    } catch (const std::invalid_argument&) {
        return true;
    }
    return false;
}

medicore::vision::XRayTensor make_tensor() {
    medicore::vision::XRayTensor tensor;
    tensor.shape = {1, 1, 4, 4};
    tensor.values = std::vector<float>(16, 0.5F);
    tensor.contract_version = "xray-core-v2/nchw-f32-0-1";
    return tensor;
}

}  // namespace

int main() {
    using medicore::vision::OnnxClassifierContract;
    using medicore::vision::validate_onnx_input_tensor;
    using medicore::vision::validate_onnx_output_width;

    const OnnxClassifierContract contract{
        .tensor_contract = "xray-core-v2/nchw-f32-0-1",
        .channels = 1,
        .height = 4,
        .width = 4,
        .label_count = 2,
    };

    const auto valid = make_tensor();
    validate_onnx_input_tensor(valid, contract);
    validate_onnx_output_width(2, contract);

    auto wrong_contract = valid;
    wrong_contract.contract_version = "legacy";
    assert(throws_invalid_argument([&]() {
        validate_onnx_input_tensor(wrong_contract, contract);
    }));

    auto wrong_shape = valid;
    wrong_shape.shape = {1, 1, 8, 2};
    assert(throws_invalid_argument([&]() {
        validate_onnx_input_tensor(wrong_shape, contract);
    }));

    auto wrong_range = valid;
    wrong_range.values[0] = 1.5F;
    assert(throws_invalid_argument([&]() {
        validate_onnx_input_tensor(wrong_range, contract);
    }));

    assert(throws_invalid_argument([&]() {
        validate_onnx_output_width(3, contract);
    }));

    return 0;
}
