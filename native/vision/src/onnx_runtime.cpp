#include "medicore_vision/onnx_runtime.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <limits>
#include <stdexcept>
#include <utility>

#ifdef MEDICORE_WITH_ONNXRUNTIME
#include <onnxruntime_cxx_api.h>
#endif

namespace medicore::vision {

#ifdef MEDICORE_WITH_ONNXRUNTIME
namespace {

struct NodeInfo {
    std::size_t index{0};
    std::vector<std::int64_t> shape;
    ONNXTensorElementDataType element_type{ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED};
};

NodeInfo find_tensor_node(
    const Ort::Session& session,
    const std::string& requested_name,
    bool input
) {
    Ort::AllocatorWithDefaultOptions allocator;
    const std::size_t count = input ? session.GetInputCount() : session.GetOutputCount();
    for (std::size_t index = 0; index < count; ++index) {
        auto allocated = input
            ? session.GetInputNameAllocated(index, allocator)
            : session.GetOutputNameAllocated(index, allocator);
        const std::string name = allocated.get() ? allocated.get() : "";
        if (name != requested_name) {
            continue;
        }
        const auto type_info = input
            ? session.GetInputTypeInfo(index)
            : session.GetOutputTypeInfo(index);
        const auto tensor_info = type_info.GetTensorTypeAndShapeInfo();
        return NodeInfo{
            index,
            tensor_info.GetShape(),
            tensor_info.GetElementType(),
        };
    }
    throw std::runtime_error(
        std::string(input ? "ONNX input not found: " : "ONNX output not found: ") + requested_name
    );
}

void validate_static_dim(
    std::int64_t actual,
    std::int64_t expected,
    const char* label
) {
    if (actual > 0 && actual != expected) {
        throw std::runtime_error(std::string("ONNX ") + label + " dimension mismatch.");
    }
}

}  // namespace
#endif

struct NativeOnnxSession::Impl {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    Ort::Env env{ORT_LOGGING_LEVEL_WARNING, "medicore-native-onnx"};
    Ort::SessionOptions options;
    Ort::Session session{nullptr};
    std::string input_name;
    std::string output_name;
    std::int64_t channels{1};
    std::int64_t height{0};
    std::int64_t width{0};
    std::size_t labels{0};
    std::int64_t static_batch{-1};
    std::size_t input_index{0};
    std::size_t output_index{0};

    Impl(
        const std::string& model_path,
        const std::string& requested_input_name,
        const std::string& requested_output_name,
        std::int64_t requested_channels,
        std::int64_t requested_height,
        std::int64_t requested_width,
        std::size_t requested_label_count,
        std::int64_t expected_batch,
        int intra_op_threads,
        int inter_op_threads
    )
        : input_name(requested_input_name),
          output_name(requested_output_name),
          channels(requested_channels),
          height(requested_height),
          width(requested_width),
          labels(requested_label_count) {
        if (model_path.empty() || input_name.empty() || output_name.empty()) {
            throw std::invalid_argument("Native ONNX model/input/output names must be non-empty.");
        }
        if (channels <= 0 || height <= 0 || width <= 0 || labels == 0) {
            throw std::invalid_argument("Native ONNX tensor dimensions must be positive.");
        }
        if (expected_batch == 0 || expected_batch < -1) {
            throw std::invalid_argument("Native ONNX expected batch must be -1 or positive.");
        }

        if (intra_op_threads > 0) {
            options.SetIntraOpNumThreads(intra_op_threads);
        }
        if (inter_op_threads > 0) {
            options.SetInterOpNumThreads(inter_op_threads);
        }
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);

        const std::filesystem::path path(model_path);
        session = Ort::Session(env, path.c_str(), options);

        const NodeInfo input = find_tensor_node(session, input_name, true);
        const NodeInfo output = find_tensor_node(session, output_name, false);
        input_index = input.index;
        output_index = output.index;

        if (input.element_type != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
            throw std::runtime_error("Native ONNX input dtype must be float32.");
        }
        if (output.element_type != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT) {
            throw std::runtime_error("Native ONNX output dtype must be float32.");
        }
        if (input.shape.size() != 4) {
            throw std::runtime_error("Native ONNX input rank must be 4 [N,C,H,W].");
        }
        if (output.shape.size() != 2) {
            throw std::runtime_error("Native ONNX output rank must be 2 [N,C].");
        }

        static_batch = input.shape[0] > 0 ? input.shape[0] : -1;
        validate_static_dim(input.shape[1], channels, "channels");
        validate_static_dim(input.shape[2], height, "height");
        validate_static_dim(input.shape[3], width, "width");
        if (expected_batch > 0 && static_batch > 0 && static_batch != expected_batch) {
            throw std::runtime_error("Native ONNX static batch does not match manifest.");
        }
        if (output.shape[1] > 0 &&
            static_cast<std::size_t>(output.shape[1]) != labels) {
            throw std::runtime_error("Native ONNX output width does not match labels.");
        }
    }

    std::vector<float> run_one(const float* data, std::size_t batch_size) const {
        const std::size_t item_elements = static_cast<std::size_t>(channels) *
            static_cast<std::size_t>(height) * static_cast<std::size_t>(width);
        const std::size_t element_count = item_elements * batch_size;

        std::vector<std::int64_t> shape{
            static_cast<std::int64_t>(batch_size), channels, height, width
        };
        auto memory_info = Ort::MemoryInfo::CreateCpu(
            OrtArenaAllocator,
            OrtMemTypeDefault
        );
        auto input_tensor = Ort::Value::CreateTensor<float>(
            memory_info,
            const_cast<float*>(data),
            element_count,
            shape.data(),
            shape.size()
        );

        const char* input_names[] = {input_name.c_str()};
        const char* output_names[] = {output_name.c_str()};
        auto outputs = session.Run(
            Ort::RunOptions{nullptr},
            input_names,
            &input_tensor,
            1,
            output_names,
            1
        );
        if (outputs.size() != 1 || !outputs[0].IsTensor()) {
            throw std::runtime_error("Native ONNX runtime returned an invalid output tensor.");
        }

        const auto info = outputs[0].GetTensorTypeAndShapeInfo();
        const auto output_shape = info.GetShape();
        if (output_shape.size() != 2 ||
            output_shape[0] != static_cast<std::int64_t>(batch_size) ||
            (output_shape[1] > 0 && static_cast<std::size_t>(output_shape[1]) != labels)) {
            throw std::runtime_error("Native ONNX output shape does not match the classifier contract.");
        }

        const std::size_t output_count = batch_size * labels;
        const float* output_data = outputs[0].GetTensorData<float>();
        if (output_data == nullptr) {
            throw std::runtime_error("Native ONNX output data is null.");
        }
        std::vector<float> result(output_data, output_data + output_count);
        if (!std::all_of(result.begin(), result.end(), [](float value) {
                return std::isfinite(value);
            })) {
            throw std::runtime_error("Native ONNX output contains NaN/Inf.");
        }
        return result;
    }
#endif
};

bool native_onnx_runtime_available() noexcept {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    return true;
#else
    return false;
#endif
}

NativeOnnxSession::NativeOnnxSession(
    const std::string& model_path,
    const std::string& input_name,
    const std::string& output_name,
    std::int64_t channels,
    std::int64_t height,
    std::int64_t width,
    std::size_t label_count,
    std::int64_t expected_batch,
    int intra_op_threads,
    int inter_op_threads
) {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    impl_ = std::make_unique<Impl>(
        model_path,
        input_name,
        output_name,
        channels,
        height,
        width,
        label_count,
        expected_batch,
        intra_op_threads,
        inter_op_threads
    );
#else
    (void)model_path;
    (void)input_name;
    (void)output_name;
    (void)channels;
    (void)height;
    (void)width;
    (void)label_count;
    (void)expected_batch;
    (void)intra_op_threads;
    (void)inter_op_threads;
    throw std::runtime_error(
        "MediCore native ONNX runtime was built without ONNX Runtime C++ libraries."
    );
#endif
}

NativeOnnxSession::~NativeOnnxSession() = default;
NativeOnnxSession::NativeOnnxSession(NativeOnnxSession&&) noexcept = default;
NativeOnnxSession& NativeOnnxSession::operator=(NativeOnnxSession&&) noexcept = default;

std::vector<float> NativeOnnxSession::run(
    const float* data,
    std::size_t element_count,
    std::size_t batch_size
) const {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    if (!impl_) {
        throw std::runtime_error("Native ONNX session is not initialized.");
    }
    if (data == nullptr || batch_size == 0) {
        throw std::invalid_argument("Native ONNX input cannot be empty.");
    }

    const std::size_t item_elements = static_cast<std::size_t>(impl_->channels) *
        static_cast<std::size_t>(impl_->height) * static_cast<std::size_t>(impl_->width);
    if (element_count != item_elements * batch_size) {
        throw std::invalid_argument("Native ONNX input element count does not match [N,C,H,W].");
    }
    for (std::size_t i = 0; i < element_count; ++i) {
        if (!std::isfinite(data[i])) {
            throw std::invalid_argument("Native ONNX input contains NaN/Inf.");
        }
    }

    if (impl_->static_batch < 0 ||
        impl_->static_batch == static_cast<std::int64_t>(batch_size)) {
        return impl_->run_one(data, batch_size);
    }
    if (impl_->static_batch == 1) {
        std::vector<float> combined;
        combined.reserve(batch_size * impl_->labels);
        for (std::size_t index = 0; index < batch_size; ++index) {
            const auto row = impl_->run_one(data + (index * item_elements), 1);
            combined.insert(combined.end(), row.begin(), row.end());
        }
        return combined;
    }
    throw std::runtime_error(
        "Native ONNX static batch is incompatible with the requested batch; padding is disabled."
    );
#else
    (void)data;
    (void)element_count;
    (void)batch_size;
    throw std::runtime_error("Native ONNX runtime is unavailable.");
#endif
}

std::int64_t NativeOnnxSession::static_input_batch() const noexcept {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    return impl_ ? impl_->static_batch : -1;
#else
    return -1;
#endif
}

std::size_t NativeOnnxSession::label_count() const noexcept {
#ifdef MEDICORE_WITH_ONNXRUNTIME
    return impl_ ? impl_->labels : 0;
#else
    return 0;
#endif
}

}  // namespace medicore::vision
