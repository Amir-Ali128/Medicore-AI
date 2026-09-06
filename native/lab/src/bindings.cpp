#include "medicore/lab/clinical_metrics.hpp"
#include "medicore/lab/lab_core.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <optional>
#include <string>
#include <vector>

namespace py = pybind11;
using medicore::lab::DerivedMetric;
using medicore::lab::LabRow;
using medicore::lab::ProcessedLabRow;

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
        return py::cast<double>(row[key]);
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

double confidence_value(const py::dict& row, const char* key) {
    const auto value = optional_double(row, key);
    return value.value_or(0.0);
}

LabRow from_python(const py::dict& row) {
    LabRow value;
    value.raw_parameter_name = text_value(row, "raw_parameter_name");
    value.canonical_name = text_value(row, "canonical_name");
    value.raw_value = text_value(row, "raw_value");
    value.normalized_value = optional_double(row, "normalized_value");
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
    value.measured_at = text_value(row, "measured_at");
    value.ai_needs_review = bool_value(row, "needs_review");
    value.extraction_confidence = confidence_value(row, "confidence");
    if (value.extraction_confidence == 0.0) {
        value.extraction_confidence = confidence_value(row, "extraction_confidence");
    }
    value.source_file_name = text_value(row, "source_file_name");
    value.source_page = optional_int(row, "source_page");
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

py::object optional_to_python(const std::optional<double>& value) {
    if (!value) {
        return py::none();
    }
    return py::float_(*value);
}

py::object optional_int_to_python(const std::optional<int>& value) {
    if (!value) {
        return py::none();
    }
    return py::int_(*value);
}

py::object text_or_none(const std::string& value) {
    if (value.empty()) {
        return py::none();
    }
    return py::str(value);
}

py::dict to_python(const ProcessedLabRow& row) {
    py::dict out;
    out["raw_parameter_name"] = row.source.raw_parameter_name;
    out["canonical_name"] = text_or_none(row.source.canonical_name);
    out["display_name"] = row.display_name;
    out["raw_value"] = text_or_none(row.source.raw_value);
    out["normalized_value"] = optional_to_python(row.source.normalized_value);
    out["unit"] = text_or_none(row.source.unit);
    out["reference_min"] = optional_to_python(row.source.reference_min);
    out["reference_max"] = optional_to_python(row.source.reference_max);
    out["reference_text"] = text_or_none(row.source.reference_text);
    out["measured_at"] = text_or_none(row.source.measured_at);
    out["source_file_name"] = text_or_none(row.source.source_file_name);
    out["source_page"] = optional_int_to_python(row.source.source_page);
    out["extraction_confidence"] = row.source.extraction_confidence;
    out["result_status"] = row.status;
    out["needs_review"] = row.needs_review;
    out["reason"] = row.reason;
    out["rule_applied"] = row.rule_applied;
    out["classification_confidence"] = row.classification_confidence;
    out["contract_version"] = medicore::lab::kContractVersion;
    return out;
}

py::dict metric_to_python(const DerivedMetric& metric) {
    py::dict out;
    out["code"] = metric.code;
    out["name"] = metric.name;
    out["value"] = metric.value;
    out["unit"] = metric.unit;
    out["formula"] = metric.formula;
    out["input_labels"] = metric.input_labels;
    out["note"] = metric.note;
    out["metrics_version"] = medicore::lab::kMetricsContractVersion;
    return out;
}

py::list process_python_rows(const py::list& rows) {
    const auto native_rows = rows_from_python(rows);
    const auto processed = medicore::lab::process_rows(native_rows);
    py::list result;
    for (const auto& row : processed) {
        result.append(to_python(row));
    }
    return result;
}

py::list compute_python_metrics(
    const py::list& rows,
    const py::object& patient_age,
    const std::string& patient_sex
) {
    const auto native_rows = rows_from_python(rows);
    const auto processed = medicore::lab::process_rows(native_rows);

    std::optional<int> age;
    if (!patient_age.is_none()) {
        try {
            age = py::cast<int>(patient_age);
        } catch (const py::cast_error&) {
            throw py::value_error("patient_age integer veya None olmalıdır.");
        }
    }

    const auto metrics = medicore::lab::compute_derived_metrics(processed, age, patient_sex);
    py::list result;
    for (const auto& metric : metrics) {
        result.append(metric_to_python(metric));
    }
    return result;
}

}  // namespace

PYBIND11_MODULE(medicore_lab, module) {
    module.doc() = "MediCore native C++ laboratory normalization/classification/metrics core";
    module.attr("CONTRACT_VERSION") = medicore::lab::kContractVersion;
    module.attr("METRICS_VERSION") = medicore::lab::kMetricsContractVersion;
    module.def("process_rows", &process_python_rows, py::arg("rows"));
    module.def("compute_derived_metrics", &compute_python_metrics, py::arg("rows"), py::arg("patient_age") = py::none(), py::arg("patient_sex") = "");
    module.def("normalize_unit", &medicore::lab::normalize_unit, py::arg("unit"));
}
