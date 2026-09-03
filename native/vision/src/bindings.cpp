#include <cstring>
#include <string>
#include <vector>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include "medicore_vision/preprocessing.hpp"

namespace py = pybind11;

namespace {

std::vector<std::uint8_t> bytes_to_vector(const py::bytes& value) {
    const std::string bytes = value;
    return std::vector<std::uint8_t>(bytes.begin(), bytes.end());
}

py::array_t<std::uint8_t> mat_to_numpy_u8(const cv::Mat& image) {
    if (image.empty() || image.type() != CV_8UC1) {
        throw std::runtime_error("expected non-empty CV_8UC1 image");
    }

    cv::Mat contiguous = image.isContinuous() ? image : image.clone();
    py::array_t<std::uint8_t> result({contiguous.rows, contiguous.cols});
    auto buffer = result.request();
    std::memcpy(
        buffer.ptr,
        contiguous.data,
        static_cast<std::size_t>(contiguous.total()));
    return result;
}

py::array_t<float> mat_to_numpy_f32(const cv::Mat& image) {
    if (image.empty() || image.type() != CV_32FC1) {
        throw std::runtime_error("expected non-empty CV_32FC1 image");
    }

    cv::Mat contiguous = image.isContinuous() ? image : image.clone();
    py::array_t<float> result({contiguous.rows, contiguous.cols});
    auto buffer = result.request();
    std::memcpy(
        buffer.ptr,
        contiguous.ptr<float>(),
        static_cast<std::size_t>(contiguous.total()) * sizeof(float));
    return result;
}

}  // namespace

PYBIND11_MODULE(medicore_vision, module) {
    module.doc() =
        "MediCore native vision primitives. Technical preprocessing only; no diagnosis.";

    module.def(
        "inspect_image",
        [](const py::bytes& encoded) {
            const auto data = bytes_to_vector(encoded);
            const cv::Mat image = medicore::vision::decode_image(data);
            const auto metadata = medicore::vision::inspect_image(image);

            py::dict result;
            result["width"] = metadata.width;
            result["height"] = metadata.height;
            result["channels"] = metadata.channels;
            result["mean_intensity"] = metadata.mean_intensity;
            result["stddev_intensity"] = metadata.stddev_intensity;
            result["min_intensity"] = metadata.min_intensity;
            result["max_intensity"] = metadata.max_intensity;
            return result;
        },
        py::arg("encoded"),
        "Decode an encoded image and return technical image metadata.");

    module.def(
        "assess_chest_xray_quality",
        [](const py::bytes& encoded) {
            const auto data = bytes_to_vector(encoded);
            const cv::Mat image = medicore::vision::decode_image(data);
            const auto metrics = medicore::vision::assess_chest_xray_quality(image);

            py::dict result;
            result["dynamic_range"] = metrics.dynamic_range;
            result["mean_intensity"] = metrics.mean_intensity;
            result["stddev_intensity"] = metrics.stddev_intensity;
            result["clipped_low_fraction"] = metrics.clipped_low_fraction;
            result["clipped_high_fraction"] = metrics.clipped_high_fraction;
            result["laplacian_variance"] = metrics.laplacian_variance;
            return result;
        },
        py::arg("encoded"),
        "Return technical chest-X-ray quality metrics without clinical interpretation.");

    module.def(
        "preprocess_chest_xray",
        [](const py::bytes& encoded, int max_side) {
            const auto data = bytes_to_vector(encoded);
            const cv::Mat image = medicore::vision::decode_image(data);
            const cv::Mat processed =
                medicore::vision::preprocess_chest_xray(image, max_side);
            return mat_to_numpy_u8(processed);
        },
        py::arg("encoded"),
        py::arg("max_side") = 2048,
        "Return a conservative grayscale chest-X-ray preprocessing result.");

    module.def(
        "prepare_chest_xray_tensor",
        [](const py::bytes& encoded, int target_size) {
            const auto data = bytes_to_vector(encoded);
            const cv::Mat image = medicore::vision::decode_image(data);
            const cv::Mat tensor =
                medicore::vision::prepare_chest_xray_tensor(image, target_size);
            return mat_to_numpy_f32(tensor);
        },
        py::arg("encoded"),
        py::arg("target_size") = 1024,
        "Return a square float32 [0,1] tensor candidate for a validated model contract.");
}
