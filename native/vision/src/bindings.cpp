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
    std::memcpy(buffer.ptr, contiguous.data, static_cast<std::size_t>(contiguous.total()));
    return result;
}

py::dict quality_to_dict(const medicore::vision::XRayQualityMetrics& quality) {
    py::dict result;
    result["width"] = quality.width;
    result["height"] = quality.height;
    result["mean_intensity"] = quality.mean_intensity;
    result["stddev_intensity"] = quality.stddev_intensity;
    result["p01_intensity"] = quality.p01_intensity;
    result["p99_intensity"] = quality.p99_intensity;
    result["robust_dynamic_range"] = quality.robust_dynamic_range;
    result["low_clip_ratio"] = quality.low_clip_ratio;
    result["high_clip_ratio"] = quality.high_clip_ratio;
    result["entropy_bits"] = quality.entropy_bits;
    result["laplacian_variance"] = quality.laplacian_variance;
    result["technical_flags"] = quality.technical_flags;
    return result;
}

py::dict transform_to_dict(const medicore::vision::TensorTransform& transform) {
    py::dict result;
    result["original_width"] = transform.original_width;
    result["original_height"] = transform.original_height;
    result["output_width"] = transform.output_width;
    result["output_height"] = transform.output_height;
    result["resized_width"] = transform.resized_width;
    result["resized_height"] = transform.resized_height;
    result["pad_left"] = transform.pad_left;
    result["pad_top"] = transform.pad_top;
    result["pad_right"] = transform.pad_right;
    result["pad_bottom"] = transform.pad_bottom;
    result["scale_x"] = transform.scale_x;
    result["scale_y"] = transform.scale_y;
    return result;
}

py::array_t<float> tensor_to_numpy(const medicore::vision::XRayTensor& tensor) {
    py::array_t<float> result({
        static_cast<py::ssize_t>(tensor.shape[0]),
        static_cast<py::ssize_t>(tensor.shape[1]),
        static_cast<py::ssize_t>(tensor.shape[2]),
        static_cast<py::ssize_t>(tensor.shape[3]),
    });
    auto buffer = result.request();
    std::memcpy(
        buffer.ptr,
        tensor.values.data(),
        tensor.values.size() * sizeof(float));
    return result;
}

}  // namespace

PYBIND11_MODULE(medicore_vision, module) {
    module.doc() = "MediCore native vision primitives. Preprocessing only; no diagnosis.";
    module.attr("__version__") = MEDICORE_VISION_VERSION;
    module.attr("XRAY_TENSOR_CONTRACT") = "xray-core-v2/nchw-f32-0-1";

    module.def(
        "inspect_image",
        [](const py::bytes& encoded) {
            const cv::Mat image = medicore::vision::decode_image(bytes_to_vector(encoded));
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
        py::arg("encoded"));

    module.def(
        "inspect_xray_quality",
        [](const py::bytes& encoded) {
            const cv::Mat image = medicore::vision::decode_image(bytes_to_vector(encoded));
            return quality_to_dict(medicore::vision::inspect_xray_quality(image));
        },
        py::arg("encoded"),
        "Return technical X-ray quality metrics and heuristic flags.");

    module.def(
        "prepare_xray_tensor",
        [](const py::bytes& encoded,
           int target_width,
           int target_height,
           bool preserve_aspect_ratio,
           int pad_value) {
            if (pad_value < 0 || pad_value > 255) {
                throw std::invalid_argument("pad_value must be between 0 and 255");
            }
            const cv::Mat image = medicore::vision::decode_image(bytes_to_vector(encoded));
            const medicore::vision::XRayPreprocessConfig config{
                .target_width = target_width,
                .target_height = target_height,
                .preserve_aspect_ratio = preserve_aspect_ratio,
                .pad_value = static_cast<std::uint8_t>(pad_value),
            };
            const auto tensor = medicore::vision::prepare_xray_tensor(image, config);
            py::dict result;
            result["tensor"] = tensor_to_numpy(tensor);
            result["shape"] = tensor.shape;
            result["layout"] = "NCHW";
            result["dtype"] = "float32";
            result["value_range"] = py::make_tuple(0.0, 1.0);
            result["contract_version"] = tensor.contract_version;
            result["transform"] = transform_to_dict(tensor.transform);
            result["quality"] = quality_to_dict(tensor.quality);
            return result;
        },
        py::arg("encoded"),
        py::arg("target_width") = 1024,
        py::arg("target_height") = 1024,
        py::arg("preserve_aspect_ratio") = true,
        py::arg("pad_value") = 0,
        "Prepare a versioned NCHW float32 [0,1] X-ray tensor with geometry metadata.");

    module.def(
        "preprocess_chest_xray",
        [](const py::bytes& encoded, int max_side) {
            const cv::Mat image = medicore::vision::decode_image(bytes_to_vector(encoded));
            return mat_to_numpy_u8(medicore::vision::preprocess_chest_xray(image, max_side));
        },
        py::arg("encoded"),
        py::arg("max_side") = 2048);
}
