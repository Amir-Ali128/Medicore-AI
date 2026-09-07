#pragma once

#include <optional>
#include <string>
#include <vector>

namespace medicore::lab {

// Keep the row contract backward-compatible with the existing Python adapter.
inline constexpr const char* kContractVersion = "medicore-lab-v1";
inline constexpr const char* kValidationContractVersion = "medicore-lab-validation-v1";

struct LabRow {
    std::string raw_parameter_name;
    std::string canonical_name;
    std::string loinc_code;
    std::string raw_value;
    std::optional<double> normalized_value;
    std::string unit;
    std::optional<double> reference_min;
    std::optional<double> reference_max;
    std::string reference_text;
    // Canonical values: range, less_than, less_equal, greater_than,
    // greater_equal, qualitative, unknown. Empty means infer conservatively.
    std::string reference_type;
    std::string measured_at;
    bool ai_needs_review{false};
    double extraction_confidence{0.0};
    std::string source_file_name;
    std::optional<int> source_page;
};

struct ProcessedLabRow {
    LabRow source;
    std::string display_name;
    std::string status;
    // VALID: deterministic classification is usable as supplied.
    // WARNING: classification exists but source extraction needs verification.
    // NEEDS_REVIEW: classification cannot safely be completed.
    // INVALID: structurally invalid input/reference data.
    std::string validation_status;
    bool needs_review{false};
    std::string reason;
    std::string rule_applied;
    double classification_confidence{0.0};
};

std::string normalize_whitespace(const std::string& value);
std::string normalize_unit(const std::string& value);
std::string normalize_reference_type(const std::string& value);
double clamp_confidence(double value);
ProcessedLabRow process_row(const LabRow& row);
std::vector<ProcessedLabRow> process_rows(const std::vector<LabRow>& rows);

}  // namespace medicore::lab
