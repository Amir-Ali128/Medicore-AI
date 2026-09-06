#pragma once

#include "medicore/lab/lab_core.hpp"

#include <optional>
#include <string>
#include <vector>

namespace medicore::lab {

inline constexpr const char* kMetricsContractVersion = "medicore-lab-metrics-v1";

struct DerivedMetric {
    std::string code;
    std::string name;
    double value{0.0};
    std::string unit;
    std::string formula;
    std::vector<std::string> input_labels;
    std::string note;
};

// Deterministic, non-diagnostic calculations derived only from confidently
// extracted laboratory values. These calculations never replace the source
// laboratory result or its printed reference interval.
std::vector<DerivedMetric> compute_derived_metrics(
    const std::vector<ProcessedLabRow>& rows,
    std::optional<int> patient_age,
    const std::string& patient_sex
);

}  // namespace medicore::lab
