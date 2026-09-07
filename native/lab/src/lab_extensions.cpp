#include "medicore/lab/lab_extensions.hpp"
#include "medicore/lab/deterministic_core.hpp"

#include <algorithm>
#include <cmath>
#include <cctype>
#include <initializer_list>
#include <regex>
#include <string>
#include <utility>
#include <vector>

namespace medicore::lab {
namespace {

std::string trim_copy(std::string value) {
    auto not_space = [](unsigned char c) { return !std::isspace(c); };
    value.erase(value.begin(), std::find_if(value.begin(), value.end(), not_space));
    value.erase(std::find_if(value.rbegin(), value.rend(), not_space).base(), value.end());
    return value;
}

std::string lower_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

std::string upper_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::toupper(c));
    });
    return value;
}

std::string replace_all(std::string value, const std::string& from, const std::string& to) {
    std::size_t pos = 0;
    while ((pos = value.find(from, pos)) != std::string::npos) {
        value.replace(pos, from.size(), to);
        pos += to.size();
    }
    return value;
}

std::string normalize_reference_text(std::string value) {
    value = trim_copy(value);
    value = replace_all(std::move(value), "≤", "<=");
    value = replace_all(std::move(value), "≥", ">=");
    value = replace_all(std::move(value), "–", "-");
    value = replace_all(std::move(value), "—", "-");
    value = replace_all(std::move(value), "−", "-");
    return trim_copy(value);
}

std::optional<double> parse_number(std::string token) {
    token = trim_copy(token);
    if (token.empty()) {
        return std::nullopt;
    }
    if (token.find(',') != std::string::npos && token.find('.') == std::string::npos) {
        std::replace(token.begin(), token.end(), ',', '.');
    }
    try {
        std::size_t used = 0;
        const double value = std::stod(token, &used);
        if (used != token.size() || !std::isfinite(value)) {
            return std::nullopt;
        }
        return value;
    } catch (const std::exception&) {
        return std::nullopt;
    }
}

bool analyte_matches(const std::string& analyte, std::initializer_list<const char*> names) {
    const std::string normalized = normalize_alias(analyte);
    for (const char* name : names) {
        if (normalized == normalize_alias(name)) {
            return true;
        }
    }
    return false;
}

UnitConversionResult unsupported_conversion(
    double value,
    std::string source,
    std::string target,
    const std::string& reason) {
    UnitConversionResult result;
    result.supported = false;
    result.converted = false;
    result.value = value;
    result.source_unit = std::move(source);
    result.target_unit = std::move(target);
    result.reason = reason;
    return result;
}

UnitConversionResult apply_linear(
    double value,
    std::string source,
    std::string target,
    double factor,
    double offset = 0.0) {
    UnitConversionResult result;
    result.supported = true;
    result.converted = source != target;
    result.value = value * factor + offset;
    result.source_unit = std::move(source);
    result.target_unit = std::move(target);
    result.reason = result.converted
        ? "Deterministic analyte-specific unit conversion applied."
        : "Units are already equivalent.";
    if (!result.value || !std::isfinite(*result.value)) {
        return unsupported_conversion(value, result.source_unit, result.target_unit, "Conversion produced a non-finite value.");
    }
    return result;
}

PlausibilityResult warning(const std::string& rule, const std::string& reason) {
    PlausibilityResult result;
    result.status = "WARNING";
    result.needs_review = true;
    result.rule_applied = rule;
    result.reason = reason;
    return result;
}

PlausibilityResult invalid(const std::string& rule, const std::string& reason) {
    PlausibilityResult result;
    result.status = "INVALID";
    result.needs_review = true;
    result.rule_applied = rule;
    result.reason = reason;
    return result;
}

bool outside(double value, double low, double high) {
    return value < low || value > high;
}

bool compatible_v2(
    const ReferenceCandidateV2& candidate,
    const std::string& patient_sex,
    const std::optional<double>& patient_age_years,
    const std::optional<bool>& pregnancy_status) {
    const std::string sex = upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex);
    const std::string patient = upper_ascii(patient_sex);
    if (sex != "ANY" && (patient.empty() || sex != patient)) {
        return false;
    }
    if (candidate.pregnancy_status.has_value() &&
        (!pregnancy_status.has_value() || *candidate.pregnancy_status != *pregnancy_status)) {
        return false;
    }
    if (candidate.age_min_years || candidate.age_max_years) {
        if (!patient_age_years || !std::isfinite(*patient_age_years) || *patient_age_years < 0.0) {
            return false;
        }
        if (candidate.age_min_years && *patient_age_years < *candidate.age_min_years) {
            return false;
        }
        if (candidate.age_max_years && *patient_age_years > *candidate.age_max_years) {
            return false;
        }
    }
    return true;
}

bool generic_v2(const ReferenceCandidateV2& candidate) {
    return upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex) == "ANY" &&
        !candidate.age_min_years && !candidate.age_max_years && !candidate.pregnancy_status.has_value();
}

double specificity_v2(const ReferenceCandidateV2& candidate) {
    double score = 0.0;
    if (upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex) != "ANY") score += 2.0;
    if (candidate.pregnancy_status.has_value()) score += 2.0;
    if (candidate.age_min_years) score += 0.5;
    if (candidate.age_max_years) score += 0.5;
    return score;
}

bool same_effective_v2(const ReferenceCandidateV2& left, const ReferenceCandidateV2& right) {
    return left.reference_min == right.reference_min &&
        left.reference_max == right.reference_max &&
        normalize_unit_semantic(left.unit) == normalize_unit_semantic(right.unit);
}

}  // namespace

std::string normalize_unit_semantic(const std::string& unit) {
    std::string value = lower_ascii(trim_copy(unit));
    value = replace_all(std::move(value), "µ", "u");
    value = replace_all(std::move(value), "μ", "u");
    value = replace_all(std::move(value), "³", "3");
    value = replace_all(std::move(value), "²", "2");
    value = replace_all(std::move(value), " ", "");
    value = replace_all(std::move(value), "per", "/");

    if (value == "mg/dl") return "mg/dL";
    if (value == "g/dl") return "g/dL";
    if (value == "mg/l") return "mg/L";
    if (value == "g/l") return "g/L";
    if (value == "mmol/l") return "mmol/L";
    if (value == "umol/l" || value == "micromol/l") return "umol/L";
    if (value == "ug/dl" || value == "mcg/dl") return "ug/dL";
    if (value == "miu/l") return "mIU/L";
    if (value == "uiu/ml") return "uIU/mL";
    if (value == "ng/ml") return "ng/mL";
    if (value == "pg/ml") return "pg/mL";
    if (value == "k/mm3" || value == "10^3/ul" || value == "10*3/ul" || value == "x10^3/ul") return "K/uL";
    if (value == "m/mm3" || value == "10^6/ul" || value == "x10^6/ul") return "M/uL";
    if (value == "%") return "%";
    if (value == "mmol/mol") return "mmol/mol";
    if (value == "meq/l") return "mEq/L";
    return trim_copy(unit);
}

ParsedReference parse_reference_text(const std::string& text) {
    ParsedReference result;
    const std::string normalized = normalize_reference_text(text);
    if (normalized.empty()) {
        result.reason = "Reference text is empty.";
        return result;
    }

    const std::string lowered = lower_ascii(normalized);
    if (lowered == "negative" || lowered == "negatif" || lowered == "non-reactive" ||
        lowered == "non reactive" || lowered == "nonreactive" || lowered == "reaktif değil" ||
        lowered == "reaktif degil") {
        result.type = "qualitative";
        result.qualitative_value = "negative";
        result.parsed = true;
        result.needs_review = false;
        result.reason = "Recognized negative/non-reactive qualitative reference.";
        return result;
    }
    if (lowered == "positive" || lowered == "pozitif" || lowered == "reactive" || lowered == "reaktif") {
        result.type = "qualitative";
        result.qualitative_value = "positive";
        result.parsed = true;
        result.needs_review = false;
        result.reason = "Recognized positive/reactive qualitative reference.";
        return result;
    }

    std::smatch match;
    static const std::regex titer_re(R"(^\s*([0-9]+)\s*:\s*([0-9]+)\s*$)");
    if (std::regex_match(normalized, match, titer_re)) {
        try {
            const int numerator = std::stoi(match[1].str());
            const int denominator = std::stoi(match[2].str());
            if (numerator > 0 && denominator > 0) {
                result.type = "qualitative";
                result.titer_numerator = numerator;
                result.titer_denominator = denominator;
                result.qualitative_value = "titer";
                result.parsed = true;
                result.needs_review = false;
                result.reason = "Recognized titer reference.";
                return result;
            }
        } catch (const std::exception&) {
        }
    }

    static const std::regex comparator_re(R"(^\s*(<=|>=|<|>)\s*([+-]?(?:[0-9]+(?:[\.,][0-9]+)?|[\.,][0-9]+))(?:\s+.*)?$)");
    if (std::regex_match(normalized, match, comparator_re)) {
        const auto number = parse_number(match[2].str());
        if (number) {
            const std::string op = match[1].str();
            if (op == "<" || op == "<=") {
                result.maximum = *number;
                result.type = op == "<" ? "less_than" : "less_equal";
            } else {
                result.minimum = *number;
                result.type = op == ">" ? "greater_than" : "greater_equal";
            }
            result.parsed = true;
            result.needs_review = false;
            result.reason = "Recognized one-sided numeric reference.";
            return result;
        }
    }

    static const std::regex range_re(R"(^\s*([+-]?(?:[0-9]+(?:[\.,][0-9]+)?|[\.,][0-9]+))\s*(?:-|to|ile)\s*([+-]?(?:[0-9]+(?:[\.,][0-9]+)?|[\.,][0-9]+))(?:\s+.*)?$)", std::regex::icase);
    if (std::regex_match(normalized, match, range_re)) {
        const auto low = parse_number(match[1].str());
        const auto high = parse_number(match[2].str());
        if (low && high) {
            result.type = "range";
            result.minimum = *low;
            result.maximum = *high;
            if (*low > *high) {
                result.reason = "Parsed range has minimum greater than maximum.";
                return result;
            }
            result.parsed = true;
            result.needs_review = false;
            result.reason = "Recognized inclusive numeric range.";
            return result;
        }
    }

    static const std::regex upto_re(R"(^\s*(?:up\s*to|en\s*fazla|maks(?:imum)?\.?)\s*([+-]?(?:[0-9]+(?:[\.,][0-9]+)?|[\.,][0-9]+))(?:\s+.*)?$)", std::regex::icase);
    if (std::regex_match(normalized, match, upto_re)) {
        const auto number = parse_number(match[1].str());
        if (number) {
            result.type = "less_equal";
            result.maximum = *number;
            result.parsed = true;
            result.needs_review = false;
            result.reason = "Recognized inclusive upper-limit reference.";
            return result;
        }
    }

    result.type = "qualitative";
    result.qualitative_value = normalized;
    result.reason = "Reference text is non-empty but not safely machine-parsable.";
    return result;
}

UnitConversionResult convert_lab_value(
    const std::string& analyte,
    double value,
    const std::string& source_unit,
    const std::string& target_unit) {
    const std::string source = normalize_unit_semantic(source_unit);
    const std::string target = normalize_unit_semantic(target_unit);
    if (!std::isfinite(value)) {
        return unsupported_conversion(value, source, target, "Non-finite values cannot be converted.");
    }
    if (source.empty() || target.empty()) {
        return unsupported_conversion(value, source, target, "Source and target units are required.");
    }
    if (source == target) {
        return apply_linear(value, source, target, 1.0);
    }

    auto reversible = [&](const char* a, const char* b, double forward_factor) -> std::optional<UnitConversionResult> {
        if (source == a && target == b) return apply_linear(value, source, target, forward_factor);
        if (source == b && target == a) return apply_linear(value, source, target, 1.0 / forward_factor);
        return std::nullopt;
    };

    if (analyte_matches(analyte, {"glucose", "glukoz", "blood glucose"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.0555)) return *r;
    }
    if (analyte_matches(analyte, {"total cholesterol", "cholesterol", "kolesterol", "ldl", "ldl cholesterol", "hdl", "hdl cholesterol"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.02586)) return *r;
    }
    if (analyte_matches(analyte, {"triglyceride", "triglycerides", "trigliserid"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.01129)) return *r;
    }
    if (analyte_matches(analyte, {"creatinine", "kreatinin"})) {
        if (auto r = reversible("mg/dL", "umol/L", 88.4)) return *r;
    }
    if (analyte_matches(analyte, {"bilirubin", "total bilirubin", "direct bilirubin", "bilirubin total", "bilirubin direct"})) {
        if (auto r = reversible("mg/dL", "umol/L", 17.104)) return *r;
    }
    if (analyte_matches(analyte, {"uric acid", "urik asit"})) {
        if (auto r = reversible("mg/dL", "umol/L", 59.48)) return *r;
    }
    if (analyte_matches(analyte, {"calcium", "kalsiyum"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.2495)) return *r;
    }
    if (analyte_matches(analyte, {"magnesium", "magnezyum"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.4114)) return *r;
    }
    if (analyte_matches(analyte, {"phosphorus", "phosphate", "fosfor", "fosfat"})) {
        if (auto r = reversible("mg/dL", "mmol/L", 0.3229)) return *r;
    }
    if (analyte_matches(analyte, {"iron", "demir"})) {
        if (auto r = reversible("ug/dL", "umol/L", 0.1791)) return *r;
    }
    if (analyte_matches(analyte, {"hba1c", "hemoglobin a1c", "glycated hemoglobin"})) {
        UnitConversionResult result;
        result.supported = true;
        result.converted = true;
        result.source_unit = source;
        result.target_unit = target;
        if (source == "%" && target == "mmol/mol") {
            result.value = (value - 2.15) * 10.929;
        } else if (source == "mmol/mol" && target == "%") {
            result.value = value / 10.929 + 2.15;
        } else {
            return unsupported_conversion(value, source, target, "No safe HbA1c conversion is registered for this unit pair.");
        }
        result.reason = "IFCC/NGSP HbA1c conversion applied deterministically.";
        return result;
    }
    if ((source == "mIU/L" && target == "uIU/mL") || (source == "uIU/mL" && target == "mIU/L")) {
        return apply_linear(value, source, target, 1.0);
    }

    return unsupported_conversion(value, source, target, "No analyte-specific deterministic conversion is registered for this unit pair.");
}

PlausibilityResult validate_plausibility(
    const std::string& analyte,
    double value,
    const std::string& unit) {
    if (!std::isfinite(value)) {
        return invalid("plausibility_non_finite", "Value is NaN or infinite.");
    }
    if (std::abs(value) > 1.0e12) {
        return warning("plausibility_extreme_magnitude", "Value magnitude is unusually large and should be verified against the source document.");
    }

    const std::string u = normalize_unit_semantic(unit);
    const bool known_nonnegative = analyte_matches(analyte, {
        "glucose", "glukoz", "creatinine", "kreatinin", "crp", "c reactive protein",
        "ferritin", "cholesterol", "total cholesterol", "ldl", "hdl", "triglyceride",
        "triglycerides", "platelet", "platelets", "plt", "wbc", "white blood cell",
        "bilirubin", "total bilirubin", "calcium", "kalsiyum", "magnesium", "magnezyum",
        "phosphorus", "phosphate", "iron", "demir", "tsh", "vitamin d", "25 oh vitamin d"
    });
    if (known_nonnegative && value < 0.0) {
        return invalid("plausibility_negative_nonnegative_analyte", "This analyte is expected to be non-negative; verify extraction and units.");
    }

    if (analyte_matches(analyte, {"sodium", "na", "sodyum"}) && (u == "mmol/L" || u == "mEq/L") && outside(value, 80.0, 220.0)) {
        return warning("plausibility_sodium_extreme", "Sodium is outside a very broad physiologic sanity band; verify source and units.");
    }
    if (analyte_matches(analyte, {"potassium", "k", "potasyum"}) && (u == "mmol/L" || u == "mEq/L") && outside(value, 1.0, 12.0)) {
        return warning("plausibility_potassium_extreme", "Potassium is outside a very broad physiologic sanity band; verify source and decimal placement.");
    }
    if (analyte_matches(analyte, {"glucose", "glukoz"}) && u == "mg/dL" && outside(value, 10.0, 2000.0)) {
        return warning("plausibility_glucose_extreme", "Glucose is outside a very broad sanity band; verify source and units.");
    }
    if (analyte_matches(analyte, {"glucose", "glukoz"}) && u == "mmol/L" && outside(value, 0.5, 111.0)) {
        return warning("plausibility_glucose_extreme", "Glucose is outside a very broad sanity band; verify source and units.");
    }
    if (analyte_matches(analyte, {"hemoglobin", "hgb", "hb"}) && u == "g/dL" && outside(value, 2.0, 25.0)) {
        return warning("plausibility_hemoglobin_extreme", "Hemoglobin is outside a very broad sanity band; verify source and units.");
    }
    if (analyte_matches(analyte, {"ph", "blood ph"}) && outside(value, 6.5, 8.0)) {
        return warning("plausibility_ph_extreme", "pH is outside a very broad biologic sanity band; verify source and specimen.");
    }
    if (analyte_matches(analyte, {"creatinine", "kreatinin"}) && u == "mg/dL" && value > 30.0) {
        return warning("plausibility_creatinine_extreme", "Creatinine is unusually high even for a broad sanity band; verify source and units.");
    }
    if (analyte_matches(analyte, {"platelet", "platelets", "plt"}) && u == "K/uL" && value > 3000.0) {
        return warning("plausibility_platelet_extreme", "Platelet count is unusually high; verify source and unit scaling.");
    }
    if (analyte_matches(analyte, {"wbc", "white blood cell", "leukocyte", "lokosit"}) && u == "K/uL" && value > 200.0) {
        return warning("plausibility_wbc_extreme", "WBC count is unusually high; verify source and unit scaling.");
    }

    PlausibilityResult result;
    result.reason = "No deterministic plausibility issue detected.";
    return result;
}

ReferenceSelectionV2 select_reference_candidate_v2(
    const std::vector<ReferenceCandidateV2>& candidates,
    const std::string& patient_sex,
    const std::optional<double>& patient_age_years,
    const std::optional<bool>& pregnancy_status) {
    ReferenceSelectionV2 out;
    if (patient_age_years && (!std::isfinite(*patient_age_years) || *patient_age_years < 0.0 || *patient_age_years > 130.0)) {
        out.reason = "Patient age is invalid or outside supported human age bounds.";
        return out;
    }

    std::vector<std::size_t> compatible_indices;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (compatible_v2(candidates[i], patient_sex, patient_age_years, pregnancy_status)) {
            compatible_indices.push_back(i);
        }
    }
    if (!compatible_indices.empty()) {
        std::stable_sort(compatible_indices.begin(), compatible_indices.end(), [&](std::size_t left, std::size_t right) {
            return specificity_v2(candidates[left]) > specificity_v2(candidates[right]);
        });
        const double best_score = specificity_v2(candidates[compatible_indices.front()]);
        std::size_t tied = 0;
        for (const auto index : compatible_indices) {
            if (specificity_v2(candidates[index]) == best_score) ++tied;
        }
        out.index = compatible_indices.front();
        out.strategy = "database_demographic";
        out.needs_review = tied > 1;
        out.confidence = out.needs_review ? 0.70 : 0.90;
        out.reason = "Matched a demographic reference range using fractional-year precision.";
        if (out.needs_review) out.reason += " Multiple equally-specific ranges matched; review needed.";
        return out;
    }

    std::vector<std::size_t> generic;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (generic_v2(candidates[i])) generic.push_back(i);
    }
    if (!generic.empty()) {
        out.index = generic.front();
        out.strategy = "database_default";
        out.needs_review = generic.size() > 1;
        out.confidence = 0.60;
        out.reason = "Using a general, input-independent reference range.";
        if (out.needs_review) out.reason += " Multiple general ranges exist; review needed.";
        return out;
    }

    std::vector<std::size_t> usable;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (candidates[i].reference_min && candidates[i].reference_max && !candidates[i].unit.empty()) usable.push_back(i);
    }
    if (!usable.empty()) {
        const auto& first = candidates[usable.front()];
        bool identical = true;
        for (const auto index : usable) {
            if (!same_effective_v2(first, candidates[index])) {
                identical = false;
                break;
            }
        }
        if (identical) {
            out.index = usable.front();
            out.strategy = "database_default";
            out.needs_review = false;
            out.confidence = 0.85;
            out.reason = "All demographic ranges have identical effective bounds and unit.";
            return out;
        }
    }

    out.reason = "No reference range is safely resolvable from the provided patient inputs.";
    return out;
}

}  // namespace medicore::lab
