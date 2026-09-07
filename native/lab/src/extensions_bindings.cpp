#include "medicore/lab/lab_extensions.hpp"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <optional>
#include <string>
#include <vector>

namespace py = pybind11;
using medicore::lab::ReferenceCandidateV2;

namespace {

py::object optional_double_to_python(const std::optional<double>& value) {
    return value ? py::cast(*value) : py::none();
}

py::object optional_int_to_python(const std::optional<int>& value) {
    return value ? py::cast(*value) : py::none();
}

std::optional<double> optional_double_object(const py::object& value) {
    if (value.is_none()) return std::nullopt;
    try {
        return py::cast<double>(value);
    } catch (const py::cast_error&) {
        throw py::value_error("Değer float veya None olmalıdır.");
    }
}

std::optional<bool> optional_bool_object(const py::object& value) {
    if (value.is_none()) return std::nullopt;
    try {
        return py::cast<bool>(value);
    } catch (const py::cast_error&) {
        throw py::value_error("Değer bool veya None olmalıdır.");
    }
}

std::optional<double> optional_double_dict(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) return std::nullopt;
    try {
        return py::cast<double>(row[key]);
    } catch (const py::cast_error&) {
        return std::nullopt;
    }
}

std::string text_dict(const py::dict& row, const char* key) {
    if (!row.contains(key) || row[key].is_none()) return {};
    return py::str(row[key]).cast<std::string>();
}

py::dict parse_reference_python(const std::string& text) {
    const auto result = medicore::lab::parse_reference_text(text);
    py::dict out;
    out["type"] = result.type;
    out["minimum"] = optional_double_to_python(result.minimum);
    out["maximum"] = optional_double_to_python(result.maximum);
    out["qualitative_value"] = result.qualitative_value.empty() ? py::none() : py::cast(result.qualitative_value);
    out["titer_numerator"] = optional_int_to_python(result.titer_numerator);
    out["titer_denominator"] = optional_int_to_python(result.titer_denominator);
    out["parsed"] = result.parsed;
    out["needs_review"] = result.needs_review;
    out["reason"] = result.reason;
    out["extensions_version"] = medicore::lab::kExtensionsContractVersion;
    return out;
}

py::dict convert_value_python(
    const std::string& analyte,
    double value,
    const std::string& source_unit,
    const std::string& target_unit) {
    const auto result = medicore::lab::convert_lab_value(analyte, value, source_unit, target_unit);
    py::dict out;
    out["supported"] = result.supported;
    out["converted"] = result.converted;
    out["value"] = optional_double_to_python(result.value);
    out["source_unit"] = result.source_unit;
    out["target_unit"] = result.target_unit;
    out["reason"] = result.reason;
    out["extensions_version"] = medicore::lab::kExtensionsContractVersion;
    return out;
}

py::dict plausibility_python(const std::string& analyte, double value, const std::string& unit) {
    const auto result = medicore::lab::validate_plausibility(analyte, value, unit);
    py::dict out;
    out["status"] = result.status;
    out["needs_review"] = result.needs_review;
    out["rule_applied"] = result.rule_applied;
    out["reason"] = result.reason;
    out["extensions_version"] = medicore::lab::kExtensionsContractVersion;
    return out;
}

py::dict select_reference_v2_python(
    const py::list& rows,
    const std::string& patient_sex,
    const py::object& patient_age_years,
    const py::object& pregnancy_status) {
    std::vector<ReferenceCandidateV2> candidates;
    candidates.reserve(static_cast<std::size_t>(py::len(rows)));
    for (const py::handle item : rows) {
        if (!py::isinstance<py::dict>(item)) {
            throw py::value_error("Her referans adayı bir dict olmalıdır.");
        }
        const py::dict row = py::reinterpret_borrow<py::dict>(item);
        ReferenceCandidateV2 candidate;
        candidate.reference_min = optional_double_dict(row, "reference_min");
        candidate.reference_max = optional_double_dict(row, "reference_max");
        candidate.unit = text_dict(row, "unit");
        candidate.source = text_dict(row, "source");
        candidate.sex = text_dict(row, "sex");
        if (candidate.sex.empty()) candidate.sex = "ANY";
        candidate.age_min_years = optional_double_dict(row, "age_min");
        candidate.age_max_years = optional_double_dict(row, "age_max");
        if (row.contains("pregnancy_status") && !row["pregnancy_status"].is_none()) {
            try {
                candidate.pregnancy_status = py::cast<bool>(row["pregnancy_status"]);
            } catch (const py::cast_error&) {
                candidate.pregnancy_status = std::nullopt;
            }
        }
        candidates.push_back(std::move(candidate));
    }

    const auto result = medicore::lab::select_reference_candidate_v2(
        candidates,
        patient_sex,
        optional_double_object(patient_age_years),
        optional_bool_object(pregnancy_status));

    py::dict out;
    out["index"] = result.index ? py::cast(*result.index) : py::none();
    out["strategy"] = result.strategy;
    out["confidence"] = result.confidence;
    out["needs_review"] = result.needs_review;
    out["reason"] = result.reason;
    out["extensions_version"] = medicore::lab::kExtensionsContractVersion;
    return out;
}

}  // namespace

PYBIND11_MODULE(medicore_lab_ext, module) {
    module.doc() = "MediCore native C++ lab extensions: reference parsing, unit conversion, plausibility, pediatric reference selection";
    module.attr("EXTENSIONS_VERSION") = medicore::lab::kExtensionsContractVersion;
    module.def("parse_reference_text", &parse_reference_python, py::arg("text"));
    module.def("normalize_unit_semantic", &medicore::lab::normalize_unit_semantic, py::arg("unit"));
    module.def("convert_lab_value", &convert_value_python,
        py::arg("analyte"), py::arg("value"), py::arg("source_unit"), py::arg("target_unit"));
    module.def("validate_plausibility", &plausibility_python,
        py::arg("analyte"), py::arg("value"), py::arg("unit"));
    module.def("select_reference_candidate_v2", &select_reference_v2_python,
        py::arg("candidates"), py::arg("patient_sex") = "",
        py::arg("patient_age_years") = py::none(), py::arg("pregnancy_status") = py::none());
}
