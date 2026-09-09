#include "medicore/lab/ai_dispatch.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <cmath>
#include <optional>
#include <string>
#include <vector>

namespace py = pybind11;
using medicore::lab::AiDispatchConfig;
using medicore::lab::AiPatientContext;
using medicore::lab::LabRow;

namespace {

std::string text_value(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) {
        return {};
    }
    return py::str(row[key]).cast<std::string>();
}

std::optional<double> optional_double(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) {
        return std::nullopt;
    }
    try {
        const double value = py::cast<double>(row[key]);
        return std::isfinite(value) ? std::optional<double>(value) : std::nullopt;
    } catch (const py::cast_error&) {
        return std::nullopt;
    }
}

std::optional<int> optional_int(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) {
        return std::nullopt;
    }
    try {
        return py::cast<int>(row[key]);
    } catch (const py::cast_error&) {
        return std::nullopt;
    }
}

std::optional<int> optional_int_object(const py::object& value) {
    if (value.is_none()) {
        return std::nullopt;
    }
    try {
        return py::cast<int>(value);
    } catch (const py::cast_error&) {
        throw py::value_error("patient_age integer veya None olmalıdır.");
    }
}

bool bool_value(const py::dict& row, const char* key, bool fallback = false) {
    if (!row.contains(key) || row[key].is_none()) {
        return fallback;
    }
    try {
        return py::cast<bool>(row[key]);
    } catch (const py::cast_error&) {
        return fallback;
    }
}

std::vector<std::string> string_list_value(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) {
        return {};
    }
    try {
        return py::cast<std::vector<std::string>>(row[key]);
    } catch (const py::cast_error&) {
        return {};
    }
}

LabRow from_python(const py::dict& row) {
    LabRow value;
    value.raw_parameter_name = text_value(row, "raw_parameter_name");
    value.canonical_name = text_value(row, "canonical_name");
    value.loinc_code = text_value(row, "loinc_code");
    value.raw_value = text_value(row, "raw_value");
    value.normalized_value = optional_double(row, "normalized_value");
    value.raw_unit = text_value(row, "raw_unit");
    value.unit = text_value(row, "unit");
    value.reference_min = optional_double(row, "reference_min");
    if (!value.reference_min) {
        value.reference_min = optional_double(row, "extracted_reference_min");
    }
    value.reference_max = optional_double(row, "reference_max");
    if (!value.reference_max) {
        value.reference_max = optional_double(row, "extracted_reference_max");
    }
    value.reference_text = text_value(row, "reference_text");
    value.reference_type = text_value(row, "reference_type");
    value.measured_at = text_value(row, "measured_at");
    value.value_type = text_value(row, "value_type");
    value.ai_needs_review = bool_value(row, "needs_review");
    value.extraction_confidence = optional_double(row, "confidence").value_or(
        optional_double(row, "extraction_confidence").value_or(0.0)
    );
    value.canonical_row_contract = text_value(row, "canonical_row_contract");
    value.source_type = text_value(row, "source_type");
    value.source_file_name = text_value(row, "source_file_name");
    value.source_page = optional_int(row, "source_page");
    value.source_sha256 = text_value(row, "source_sha256");
    value.source_record_id = text_value(row, "source_record_id");
    value.integration_type = text_value(row, "integration_type");
    value.ingestion_reasons = string_list_value(row, "ingestion_reasons");
    return value;
}

std::vector<LabRow> rows_from_python(const py::list& rows) {
    std::vector<LabRow> native_rows;
    native_rows.reserve(static_cast<std::size_t>(py::len(rows)));
    for (const py::handle item : rows) {
        if (!py::isinstance<py::dict>(item)) {
            throw py::value_error("Her laboratuvar satırı bir dict olmalıdır.");
        }
        native_rows.push_back(from_python(py::reinterpret_borrow<py::dict>(item)));
    }
    return native_rows;
}

AiPatientContext patient_context(const py::object& age, const std::string& sex) {
    AiPatientContext patient;
    patient.age = optional_int_object(age);
    patient.sex = sex;
    return patient;
}

std::string build_request_python(
    const py::list& rows,
    const py::object& patient_age,
    const std::string& patient_sex,
    const std::string& model,
    int max_output_tokens
) {
    const auto native_rows = rows_from_python(rows);
    const auto processed = medicore::lab::process_rows(native_rows);
    return medicore::lab::build_openai_lab_request(
        processed,
        patient_context(patient_age, patient_sex),
        model,
        max_output_tokens
    );
}

py::dict dispatch_python(
    const py::list& rows,
    const py::object& patient_age,
    const std::string& patient_sex,
    const std::string& api_key,
    const std::string& model,
    const std::string& endpoint,
    double timeout_seconds,
    int max_output_tokens
) {
    if (!std::isfinite(timeout_seconds) || timeout_seconds <= 0.0) {
        throw py::value_error("timeout_seconds pozitif olmalıdır.");
    }

    AiDispatchConfig config;
    config.api_key = api_key;
    config.model = model;
    config.endpoint = endpoint;
    config.timeout_ms = static_cast<long>(timeout_seconds * 1000.0);
    config.max_output_tokens = max_output_tokens;

    // Release the GIL during the blocking provider HTTPS call.
    const auto native_rows = rows_from_python(rows);
    const auto patient = patient_context(patient_age, patient_sex);
    medicore::lab::AiDispatchResult result;
    {
        py::gil_scoped_release release;
        result = medicore::lab::dispatch_all_lab_rows_to_ai(native_rows, patient, config);
    }

    py::dict out;
    out["contract_version"] = medicore::lab::kAiDispatchContractVersion;
    out["http_status"] = result.http_status;
    out["model"] = result.model;
    out["response_body"] = result.response_body;
    return out;
}

}  // namespace

PYBIND11_MODULE(medicore_lab_ai, module) {
    module.doc() = "MediCore native C++ direct laboratory-to-AI transport";
    module.attr("AI_DISPATCH_VERSION") = medicore::lab::kAiDispatchContractVersion;
    module.attr("HTTP_AVAILABLE") = medicore::lab::ai_http_transport_available();
    module.def(
        "build_request",
        &build_request_python,
        py::arg("rows"),
        py::arg("patient_age") = py::none(),
        py::arg("patient_sex") = "",
        py::arg("model") = "gpt-5.6-luna",
        py::arg("max_output_tokens") = 3200
    );
    module.def(
        "dispatch_all_rows",
        &dispatch_python,
        py::arg("rows"),
        py::arg("patient_age") = py::none(),
        py::arg("patient_sex") = "",
        py::arg("api_key"),
        py::arg("model"),
        py::arg("endpoint") = "https://api.openai.com/v1/responses",
        py::arg("timeout_seconds") = 45.0,
        py::arg("max_output_tokens") = 3200
    );
}
