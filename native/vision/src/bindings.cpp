#include <array>
#include <cstring>
#include <optional>
#include <string>
#include <vector>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "medicore_vision/dicom_engine.hpp"
#include "medicore_vision/postprocessing.hpp"
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

cv::Mat numpy_to_mat_f32(const py::array& value) {
    py::array_t<float, py::array::c_style | py::array::forcecast> typed(value);
    const auto buffer = typed.request();
    if (buffer.ndim != 2 || buffer.shape[0] <= 0 || buffer.shape[1] <= 0) {
        throw std::invalid_argument("spatial_map must be a non-empty 2D array");
    }
    cv::Mat view(
        static_cast<int>(buffer.shape[0]),
        static_cast<int>(buffer.shape[1]),
        CV_32FC1,
        buffer.ptr);
    return view.clone();
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

medicore::vision::TensorTransform transform_from_dict(const py::dict& value) {
    auto get_int = [&value](const char* key) -> int {
        if (!value.contains(py::str(key))) {
            throw std::invalid_argument(std::string("transform missing field: ") + key);
        }
        return value[py::str(key)].cast<int>();
    };
    auto get_double = [&value](const char* key) -> double {
        if (!value.contains(py::str(key))) {
            throw std::invalid_argument(std::string("transform missing field: ") + key);
        }
        return value[py::str(key)].cast<double>();
    };

    medicore::vision::TensorTransform transform{
        .original_width = get_int("original_width"),
        .original_height = get_int("original_height"),
        .output_width = get_int("output_width"),
        .output_height = get_int("output_height"),
        .resized_width = get_int("resized_width"),
        .resized_height = get_int("resized_height"),
        .pad_left = get_int("pad_left"),
        .pad_top = get_int("pad_top"),
        .pad_right = get_int("pad_right"),
        .pad_bottom = get_int("pad_bottom"),
        .scale_x = get_double("scale_x"),
        .scale_y = get_double("scale_y"),
    };
    medicore::vision::validate_tensor_transform(transform);
    return transform;
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

py::dict dicom_metadata_to_dict(const medicore::vision::DicomMetadata& metadata) {
    py::dict result;
    result["rows"] = metadata.rows;
    result["columns"] = metadata.columns;
    result["frames"] = metadata.frames;
    result["samples_per_pixel"] = metadata.samples_per_pixel;
    result["bits_allocated"] = metadata.bits_allocated;
    result["bits_stored"] = metadata.bits_stored;
    result["high_bit"] = metadata.high_bit;
    result["pixel_representation"] = metadata.pixel_representation;
    result["modality"] = metadata.modality;
    result["photometric_interpretation"] = metadata.photometric_interpretation;
    result["transfer_syntax"] = metadata.transfer_syntax;
    result["transfer_syntax_uid"] = metadata.transfer_syntax_uid;
    result["compressed"] = metadata.compressed;
    result["rescale_slope"] = metadata.rescale_slope;
    result["rescale_intercept"] = metadata.rescale_intercept;
    result["has_window"] = metadata.has_window;
    result["window_center"] = metadata.has_window ? py::cast(metadata.window_center) : py::none();
    result["window_width"] = metadata.has_window ? py::cast(metadata.window_width) : py::none();
    result["native_pixel_decode_supported"] = !metadata.compressed;
    return result;
}

medicore::vision::DicomWindowConfig dicom_window_from_python(
    const py::object& center,
    const py::object& width) {
    medicore::vision::DicomWindowConfig config;
    if (!center.is_none()) {
        config.center = center.cast<double>();
    }
    if (!width.is_none()) {
        config.width = width.cast<double>();
    }
    return config;
}

py::dict dicom_frame_context(const medicore::vision::DicomFrame& frame) {
    py::dict window;
    window["source"] = frame.window_source;
    window["center"] = frame.applied_window_center;
    window["width"] = frame.applied_window_width;
    window["modality_min"] = frame.modality_min;
    window["modality_max"] = frame.modality_max;

    py::dict result;
    result["frame_index"] = frame.frame_index;
    result["metadata"] = dicom_metadata_to_dict(frame.metadata);
    result["window"] = window;
    result["source_contract"] = frame.contract_version;
    return result;
}

py::object optional_double_to_python(const std::optional<double>& value) {
    return value ? py::cast(*value) : py::none();
}

py::list regions_to_python(const std::vector<medicore::vision::RegionMeasurement>& regions) {
    py::list result;
    for (const auto& region : regions) {
        py::dict item;
        item["component_id"] = region.component_id;
        item["bbox"] = py::dict(
            "x"_a = region.x,
            "y"_a = region.y,
            "width"_a = region.width,
            "height"_a = region.height);
        item["area_pixels"] = region.area_pixels;
        item["area_fraction"] = region.area_fraction;
        item["centroid"] = py::make_tuple(region.centroid_x, region.centroid_y);
        item["mean_score"] = region.mean_score;
        item["peak_score"] = region.peak_score;
        item["area_mm2"] = optional_double_to_python(region.area_mm2);
        item["bbox_width_mm"] = optional_double_to_python(region.bbox_width_mm);
        item["bbox_height_mm"] = optional_double_to_python(region.bbox_height_mm);
        result.append(item);
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(medicore_vision, module) {
    using namespace pybind11::literals;

    module.doc() = "MediCore native medical-image primitives. Technical processing only; no diagnosis.";
    module.attr("__version__") = MEDICORE_VISION_VERSION;
    module.attr("XRAY_TENSOR_CONTRACT") = "xray-core-v2/nchw-f32-0-1";
    module.attr("DICOM_FRAME_CONTRACT") = medicore::vision::kDicomFrameContract;
    module.attr("VISION_POSTPROCESS_CONTRACT") = medicore::vision::kVisionPostprocessContract;

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
        "inspect_dicom",
        [](const py::bytes& encoded) {
            const auto metadata = medicore::vision::inspect_dicom(bytes_to_vector(encoded));
            return dicom_metadata_to_dict(metadata);
        },
        py::arg("encoded"),
        "Inspect technical DICOM metadata without exposing patient identifiers.");

    module.def(
        "prepare_dicom_frame",
        [](const py::bytes& encoded,
           int frame_index,
           const py::object& window_center,
           const py::object& window_width) {
            const auto frame = medicore::vision::decode_dicom_frame(
                bytes_to_vector(encoded),
                frame_index,
                dicom_window_from_python(window_center, window_width));
            py::dict result = dicom_frame_context(frame);
            result["image"] = mat_to_numpy_u8(frame.image);
            result["shape"] = py::make_tuple(frame.image.rows, frame.image.cols);
            result["dtype"] = "uint8";
            result["value_range"] = py::make_tuple(0, 255);
            result["contract_version"] = frame.contract_version;
            return result;
        },
        py::arg("encoded"),
        py::arg("frame_index") = 0,
        py::arg("window_center") = py::none(),
        py::arg("window_width") = py::none(),
        "Decode one DICOM frame through rescale/windowing/MONOCHROME handling.");

    module.def(
        "prepare_dicom_xray_tensor",
        [](const py::bytes& encoded,
           int frame_index,
           const py::object& window_center,
           const py::object& window_width,
           int target_width,
           int target_height,
           bool preserve_aspect_ratio,
           int pad_value) {
            if (pad_value < 0 || pad_value > 255) {
                throw std::invalid_argument("pad_value must be between 0 and 255");
            }
            const auto frame = medicore::vision::decode_dicom_frame(
                bytes_to_vector(encoded),
                frame_index,
                dicom_window_from_python(window_center, window_width));
            if (!medicore::vision::is_xray_dicom_modality(frame.metadata.modality)) {
                throw std::invalid_argument(
                    "DICOM modality is not CR/DX; refusing to feed it into the X-Ray tensor contract");
            }
            const medicore::vision::XRayPreprocessConfig config{
                .target_width = target_width,
                .target_height = target_height,
                .preserve_aspect_ratio = preserve_aspect_ratio,
                .pad_value = static_cast<std::uint8_t>(pad_value),
            };
            const auto tensor = medicore::vision::prepare_xray_tensor(frame.image, config);
            py::dict result = dicom_frame_context(frame);
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
        py::arg("frame_index") = 0,
        py::arg("window_center") = py::none(),
        py::arg("window_width") = py::none(),
        py::arg("target_width") = 1024,
        py::arg("target_height") = 1024,
        py::arg("preserve_aspect_ratio") = true,
        py::arg("pad_value") = 0,
        "Decode CR/DX DICOM and prepare the X-Ray Core v2 tensor contract.");

    module.def(
        "map_model_box_to_original",
        [](const std::array<double, 4>& box, const py::dict& transform, bool clip) {
            const auto mapped = medicore::vision::map_model_box_to_original(
                medicore::vision::BoxF{
                    .x1 = box[0],
                    .y1 = box[1],
                    .x2 = box[2],
                    .y2 = box[3],
                },
                transform_from_dict(transform),
                clip);
            return py::make_tuple(mapped.x1, mapped.y1, mapped.x2, mapped.y2);
        },
        py::arg("box"),
        py::arg("transform"),
        py::arg("clip") = true,
        "Map an xyxy model-space box through letterbox geometry into original pixels.");

    module.def(
        "postprocess_spatial_map",
        [](const py::array& spatial_map,
           const py::dict& transform,
           double threshold,
           int min_component_area,
           int max_components,
           bool normalize_minmax,
           const py::object& pixel_spacing_row_mm,
           const py::object& pixel_spacing_col_mm) {
            medicore::vision::SpatialPostprocessConfig config{
                .threshold = threshold,
                .min_component_area = min_component_area,
                .max_components = max_components,
                .normalize_minmax = normalize_minmax,
            };
            if (!pixel_spacing_row_mm.is_none()) {
                config.pixel_spacing_row_mm = pixel_spacing_row_mm.cast<double>();
            }
            if (!pixel_spacing_col_mm.is_none()) {
                config.pixel_spacing_col_mm = pixel_spacing_col_mm.cast<double>();
            }

            const auto result = medicore::vision::postprocess_spatial_map(
                numpy_to_mat_f32(spatial_map),
                transform_from_dict(transform),
                config);
            py::dict payload;
            payload["heatmap"] = mat_to_numpy_f32(result.heatmap_original);
            payload["mask"] = mat_to_numpy_u8(result.mask_original);
            payload["shape"] = py::make_tuple(
                result.heatmap_original.rows,
                result.heatmap_original.cols);
            payload["heatmap_dtype"] = "float32";
            payload["mask_dtype"] = "uint8";
            payload["heatmap_range"] = py::make_tuple(0.0, 1.0);
            payload["mask_values"] = py::make_tuple(0, 255);
            payload["regions"] = regions_to_python(result.regions);
            payload["contract_version"] = result.contract_version;
            return payload;
        },
        py::arg("spatial_map"),
        py::arg("transform"),
        py::arg("threshold") = 0.5,
        py::arg("min_component_area") = 16,
        py::arg("max_components") = 32,
        py::arg("normalize_minmax") = true,
        py::arg("pixel_spacing_row_mm") = py::none(),
        py::arg("pixel_spacing_col_mm") = py::none(),
        "Map a model heatmap/mask into original pixels and extract regions/measurements.");

    module.def(
        "preprocess_chest_xray",
        [](const py::bytes& encoded, int max_side) {
            const cv::Mat image = medicore::vision::decode_image(bytes_to_vector(encoded));
            return mat_to_numpy_u8(medicore::vision::preprocess_chest_xray(image, max_side));
        },
        py::arg("encoded"),
        py::arg("max_side") = 2048);
}
