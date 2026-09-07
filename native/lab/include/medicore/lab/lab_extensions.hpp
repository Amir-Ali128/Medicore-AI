#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace medicore::lab {

inline constexpr const char* kExtensionsContractVersion = "medicore-lab-extensions-v1";

struct ParsedReference {
    std::string type{"unknown"};
    std::optional<double> minimum;
    std::optional<double> maximum;
    std::string qualitative_value;
    std::optional<int> titer_numerator;
    std::optional<int> titer_denominator;
    bool parsed{false};
    bool needs_review{true};
    std::string reason;
};

struct UnitConversionResult {
    bool supported{false};
    bool converted{false};
    std::optional<double> value;
    std::string source_unit;
    std::string target_unit;
    std::string reason;
};

struct PlausibilityResult {
    std::string status{"VALID"};
    bool needs_review{false};
    std::string rule_applied{"plausibility_ok"};
    std::string reason;
};

struct ReferenceCandidateV2 {
    std::optional<double> reference_min;
    std::optional<double> reference_max;
    std::string unit;
    std::string source;
    std::string sex{"ANY"};
    // Ages are represented as decimal years so neonatal/pediatric fractional
    // ranges (for example 7 days ~= 0.0192 years) are not rounded to integers.
    std::optional<double> age_min_years;
    std::optional<double> age_max_years;
    std::optional<bool> pregnancy_status;
};

struct ReferenceSelectionV2 {
    std::optional<std::size_t> index;
    std::string strategy{"needs_review"};
    double confidence{0.0};
    bool needs_review{true};
    std::string reason;
};

ParsedReference parse_reference_text(const std::string& text);

UnitConversionResult convert_lab_value(
    const std::string& analyte,
    double value,
    const std::string& source_unit,
    const std::string& target_unit);

PlausibilityResult validate_plausibility(
    const std::string& analyte,
    double value,
    const std::string& unit);

ReferenceSelectionV2 select_reference_candidate_v2(
    const std::vector<ReferenceCandidateV2>& candidates,
    const std::string& patient_sex,
    const std::optional<double>& patient_age_years,
    const std::optional<bool>& pregnancy_status);

std::string normalize_unit_semantic(const std::string& unit);

}  // namespace medicore::lab
