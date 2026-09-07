#include "medicore/lab/clinical_metrics.hpp"
#include "medicore/lab/deterministic_core.hpp"
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
using medicore::lab::ReferenceCandidate;

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

std::optional<double> optional_double_object(const py::object& value) {
    if (value.is_none()) {
        return std::nullopt;
    }
    try {
        return py::cast<double>(value);
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
        throw py::value_error("Değer integer veya None olmalıdır.");
    }
}

std::optional<bool> optional_bool_object(const py::object& value) {
    if (value.is_none()) {
        return std::nullopt;
    }
    try {
        return py::cast<bool>(value);
    } catch (const py::cast_error&) {
        throw py::value_error("Değer bool veya None olmalıdır.");
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
    value.loinc_code = text_value(row, "loinc_code");
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
    value.reference_type = text_value(row, "reference_type");
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

ReferenceCandidate reference_candidate_from_python(const py::dict& row) {
    ReferenceCandidate candidate;
    candidate.reference_min = optional_double(row, "reference_min");
    candidate.reference_max = optional_double(row, "reference_max");
    candidate.unit = text_value(row, "unit");
    candidate.source = text_value(row, "source");
    candidate.sex = text_value(row, "sex");
    if (candidate.sex.empty()) {
        candidate.sex = "ANY";
    }
    candidate.age_min = optional_int(row, "age_min");
    candidate.age_max = optional_int(row, "age_max");
    if (row.contains("pregnancy_status") && !row["pregnancy_status"].is_none()) {
        try {
            candidate.pregnancy_status = py::cast<bool>(row["pregnancy_status"]);
        } catch (const py::cast_error&) {
            candidate.pregnancy_status = std::nullopt;
        }
    }
    return candidate;
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

py::object optional_index_to_python(const std::optional<std::size_t>& value) {
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
    out["loinc_code"] = text_or_none(row.source.loinc_code);
    out["display_name"] = row.display_name;
    out["raw_value"] = text_or_none(row.source.raw_value);
    out["normalized_value"] = optional_to_python(row.source.normalized_value);
    out["unit"] = text_or_none(row.source.unit);
    out["reference_min"] = optional_to_python(row.source.reference_min);
    out["reference_max"] = optional_to_python(row.source.reference_max);
    out["reference_text"] = text_or_none(row.source.reference_text);
    out["reference_type"] = row.source.reference_type;
    out["measured_at"] = text_or_none(row.source.measured_at);
    out["source_file_name"] = text_or_none(row.source.source_file_name);
    out["source_page"] = optional_int_to_python(row.source.source_page);
    out["extraction_confidence"] = row.source.extraction_confidence;
    out["result_status"] = row.status;
    out["validation_status"] = row.validation_status;
    out["needs_review"] = row.needs_review;
    out["reason"] = row.reason;
    out["rule_applied"] = row.rule_applied;
    out["classification_confidence"] = row.classification_confidence;
    out["contract_version"] = medicore::lab::kContractVersion;
    out["validation_contract_version"] = medicore::lab::kValidationContractVersion;
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
    const auto age = optional_int_object(patient_age);
    const auto metrics = medicore::lab::compute_derived_metrics(processed, age, patient_sex);
    py::list result;
    for (const auto& metric : metrics) {
        result.append(metric_to_python(metric));
    }
    return result;
}

py::dict evaluate_rule_python(
    bool parameter_known,
    bool alias_needs_review,
    bool reference_needs_review,
    const py::object& normalized_value,
    const py::object& reference_min,
    const py::object& reference_max
) {
    const auto result = medicore::lab::evaluate_rule(
        parameter_known,
        alias_needs_review,
        reference_needs_review,
        optional_double_object(normalized_value),
        optional_double_object(reference_min),
        optional_double_object(reference_max)
    );
    py::dict out;
    out["status"] = result.status;
    out["reason"] = result.reason;
    out["rule_applied"] = result.rule_applied;
    out["confidence"] = result.confidence;
    out["needs_review"] = result.needs_review;
    out["deterministic_version"] = medicore::lab::kDeterministicContractVersion;
    return out;
}

py::dict compare_trend_python(
    const py::object& current_value,
    const py::object& previous_value,
    const py::object& time_difference_days,
    double stable_relative_threshold
) {
    const auto result = medicore::lab::compare_trend(
        optional_double_object(current_value),
        optional_double_object(previous_value),
        optional_int_object(time_difference_days),
        stable_relative_threshold
    );
    py::dict out;
    out["status"] = result.status;
    out["previous_value"] = optional_to_python(result.previous_value);
    out["current_value"] = optional_to_python(result.current_value);
    out["absolute_difference"] = optional_to_python(result.absolute_difference);
    out["percentage_difference"] = optional_to_python(result.percentage_difference);
    out["time_difference_days"] = optional_int_to_python(result.time_difference_days);
    out["confidence"] = result.confidence;
    out["reason"] = result.reason;
    out["needs_review"] = result.needs_review;
    out["deterministic_version"] = medicore::lab::kDeterministicContractVersion;
    return out;
}

py::dict select_reference_python(
    const py::list& rows,
    const std::string& patient_sex,
    const py::object& patient_age,
    const py::object& pregnancy_status
) {
    std::vector<ReferenceCandidate> candidates;
    candidates.reserve(static_cast<std::size_t>(py::len(rows)));
    for (const py::handle item : rows) {
        if (!py::isinstance<py::dict>(item)) {
            throw py::value_error("Her referans adayı bir dict olmalıdır.");
        }
        candidates.push_back(reference_candidate_from_python(py::reinterpret_borrow<py::dict>(item)));
    }
    const auto selection = medicore::lab::select_reference_candidate(
        candidates,
        patient_sex,
        optional_int_object(patient_age),
        optional_bool_object(pregnancy_status)
    );
    py::dict out;
    out["index"] = optional_index_to_python(selection.index);
    out["strategy"] = selection.strategy;
    out["confidence"] = selection.confidence;
    out["needs_review"] = selection.needs_review;
    out["reason"] = selection.reason;
    out["deterministic_version"] = medicore::lab::kDeterministicContractVersion;
    return out;
}

}  // namespace

PYBIND11_MODULE(medicore_lab, module) {
    module.doc() = "MediCore native C++ laboratory normalization/classification/metrics core";
    module.attr("CONTRACT_VERSION") = medicore::lab::kContractVersion;
    module.attr("VALIDATION_VERSION") = medicore::lab::kValidationContractVersion;
    module.attr("METRICS_VERSION") = medicore::lab::kMetricsContractVersion;
    module.attr("DETERMINISTIC_VERSION") = medicore::lab::kDeterministicContractVersion;
    module.def("process_rows", &process_python_rows, py::arg("rows"));
    module.def("compute_derived_metrics", &compute_python_metrics, py::arg("rows"), py::arg("patient_age") = py::none(), py::arg("patient_sex") = "");
    module.def("normalize_unit", &medicore::lab::normalize_unit, py::arg("unit"));
    module.def("normalize_reference_type", &medicore::lab::normalize_reference_type, py::arg("reference_type"));
    module.def("normalize_alias", &medicore::lab::normalize_alias, py::arg("value"));
    module.def("alias_similarity_ratio", &medicore::lab::alias_similarity_ratio, py::arg("left"), py::arg("right"));
    module.def("evaluate_rule", &evaluate_rule_python,
        py::arg("parameter_known"), py::arg("alias_needs_review"), py::arg("reference_needs_review"),
        py::arg("normalized_value") = py::none(), py::arg("reference_min") = py::none(), py::arg("reference_max") = py::none());
    module.def("compare_trend", &compare_trend_python,
        py::arg("current_value") = py::none(), py::arg("previous_value") = py::none(),
        py::arg("time_difference_days") = py::none(), py::arg("stable_relative_threshold") = 0.05);
    module.def("select_reference_candidate", &select_reference_python,
        py::arg("candidates"), py::arg("patient_sex") = "", py::arg("patient_age") = py::none(), py::arg("pregnancy_status") = py::none());
}
