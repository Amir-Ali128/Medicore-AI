#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace medicore::lab {

inline constexpr const char* kDeterministicContractVersion = "medicore-lab-deterministic-v1";

struct RuleEvaluation {
    std::string status{"UNKNOWN"};
    std::string reason;
    std::string rule_applied;
    double confidence{0.0};
    bool needs_review{true};
};

struct TrendEvaluation {
    std::string status{"NO_PREVIOUS_RESULT"};
    std::optional<double> previous_value;
    std::optional<double> current_value;
    std::optional<double> absolute_difference;
    std::optional<double> percentage_difference;
    std::optional<int> time_difference_days;
    double confidence{0.0};
    std::string reason;
    bool needs_review{false};
};

struct ReferenceCandidate {
    std::optional<double> reference_min;
    std::optional<double> reference_max;
    std::string unit;
    std::string source;
    std::string sex{"ANY"};
    std::optional<double> age_min;
    std::optional<double> age_max;
    std::optional<bool> pregnancy_status;
};

struct ReferenceSelection {
    std::optional<std::size_t> index;
    std::string strategy{"needs_review"};
    double confidence{0.0};
    bool needs_review{true};
    std::string reason;
};

std::string normalize_alias(const std::string& value);
double alias_similarity_ratio(const std::string& left, const std::string& right);

RuleEvaluation evaluate_rule(
    bool parameter_known,
    bool alias_needs_review,
    bool reference_needs_review,
    const std::optional<double>& normalized_value,
    const std::optional<double>& reference_min,
    const std::optional<double>& reference_max);

TrendEvaluation compare_trend(
    const std::optional<double>& current_value,
    const std::optional<double>& previous_value,
    const std::optional<int>& time_difference_days,
    double stable_relative_threshold = 0.05);

ReferenceSelection select_reference_candidate(
    const std::vector<ReferenceCandidate>& candidates,
    const std::string& patient_sex,
    const std::optional<double>& patient_age,
    const std::optional<bool>& pregnancy_status);

}  // namespace medicore::lab
