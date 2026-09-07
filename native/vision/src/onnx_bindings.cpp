#include "medicore_vision/onnx_runtime.hpp"

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace {

py::array_t<float> run_numpy(
    const medicore::vision::NativeOnnxSession& session,
    py::array_t<float, py::array::c_style | py::array::forcecast> batch
) {
    const py::buffer_info info = batch.request();
    if (info.ndim != 4) {
        throw py::value_error("Native ONNX input rank 4 [N,C,H,W] olmalıdır.");
    }
    if (info.shape[0] < 1) {
        throw py::value_error("Native ONNX batch boş olamaz.");
    }

    const auto output = session.run(
        static_cast<const float*>(info.ptr),
        static_cast<std::size_t>(info.size),
        static_cast<std::size_t>(info.shape[0])
    );
    const std::size_t labels = session.label_count();
    if (labels == 0 || output.size() != static_cast<std::size_t>(info.shape[0]) * labels) {
        throw std::runtime_error("Native ONNX output size contract mismatch.");
    }

    py::array_t<float> result({
        static_cast<py::ssize_t>(info.shape[0]),
        static_cast<py::ssize_t>(labels),
    });
    py::buffer_info out_info = result.request();
    float* out_ptr = static_cast<float*>(out_info.ptr);
    std::copy(output.begin(), output.end(), out_ptr);
    return result;
}

}  // namespace

PYBIND11_MODULE(medicore_onnx, module) {
    module.doc() = "MediCore optional native C++ ONNX Runtime hot path";
    module.attr("CONTRACT_VERSION") = medicore::vision::kNativeOnnxContractVersion;
    module.attr("AVAILABLE") = medicore::vision::native_onnx_runtime_available();
    module.def("runtime_available", &medicore::vision::native_onnx_runtime_available);

    py::class_<medicore::vision::NativeOnnxSession>(module, "NativeOnnxSession")
        .def(
            py::init<
                const std::string&,
                const std::string&,
                const std::string&,
                std::int64_t,
                std::int64_t,
                std::int64_t,
                std::size_t,
                std::int64_t,
                int,
                int>(),
            py::arg("model_path"),
            py::arg("input_name"),
            py::arg("output_name"),
            py::arg("channels"),
            py::arg("height"),
            py::arg("width"),
            py::arg("label_count"),
            py::arg("expected_batch") = -1,
            py::arg("intra_op_threads") = 0,
            py::arg("inter_op_threads") = 0
        )
        .def("run", &run_numpy, py::arg("batch"))
        .def_property_readonly("static_input_batch", &medicore::vision::NativeOnnxSession::static_input_batch)
        .def_property_readonly("label_count", &medicore::vision::NativeOnnxSession::label_count);
}
