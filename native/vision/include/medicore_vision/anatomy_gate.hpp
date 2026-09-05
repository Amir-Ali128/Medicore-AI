#pragma once

#include <string>
#include <vector>

namespace medicore::vision {

inline constexpr const char* kAnatomyGateContract = "anatomy-gate-v1";

enum class AnatomyConfidenceLevel {
    Low,
    Moderate,
    High,
};

struct AnatomyCandidate {
    std::string label;
    double confidence{0.0};
};

struct AnatomyGateConfig {
    double classifier_high{0.85};
    double classifier_moderate{0.60};
    double segmentation_min{0.80};
    double landmark_min{0.75};
    double minimum_margin{0.10};
};

struct AnatomyAssessment {
    std::string best_label{"UNKNOWN"};
    double classifier_confidence{0.0};
    double runner_up_confidence{0.0};
    double margin{0.0};
    double segmentation_confidence{-1.0};
    double landmark_confidence{-1.0};
    AnatomyConfidenceLevel level{AnatomyConfidenceLevel::Low};
    bool anatomy_identified{false};
    bool organ_specific_report_allowed{false};
    std::string report_phrase_tr{"Anatomik yapı güvenilir biçimde tanımlanamadı."};
};

[[nodiscard]] AnatomyAssessment assess_anatomy(
    const std::vector<AnatomyCandidate>& candidates,
    double segmentation_confidence = -1.0,
    double landmark_confidence = -1.0,
    const AnatomyGateConfig& config = {});

[[nodiscard]] const char* anatomy_confidence_level_name(AnatomyConfidenceLevel level) noexcept;

}  // namespace medicore::vision
