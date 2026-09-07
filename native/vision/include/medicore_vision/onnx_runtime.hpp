#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace medicore::vision {

inline constexpr const char* kNativeOnnxContractVersion = "medicore-native-onnx-v1";

bool native_onnx_runtime_available() noexcept;

class NativeOnnxSession {
public:
    NativeOnnxSession(
        const std::string& model_path,
        const std::string& input_name,
        const std::string& output_name,
        std::int64_t channels,
        std::int64_t height,
        std::int64_t width,
        std::size_t label_count,
        std::int64_t expected_batch,
        int intra_op_threads = 0,
        int inter_op_threads = 0);

    ~NativeOnnxSession();
    NativeOnnxSession(NativeOnnxSession&&) noexcept;
    NativeOnnxSession& operator=(NativeOnnxSession&&) noexcept;
    NativeOnnxSession(const NativeOnnxSession&) = delete;
    NativeOnnxSession& operator=(const NativeOnnxSession&) = delete;

    std::vector<float> run(
        const float* data,
        std::size_t element_count,
        std::size_t batch_size) const;

    std::int64_t static_input_batch() const noexcept;
    std::size_t label_count() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

}  // namespace medicore::vision
