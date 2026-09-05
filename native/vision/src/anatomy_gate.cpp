#include "medicore_vision/anatomy_gate.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <unordered_set>

namespace medicore::vision {
namespace {

void validate_probability(double value, const char* name, bool allow_unavailable = false) {
    if (allow_unavailable && value < 0.0) {
        return;
    }
    if (!std::isfinite(value) || value < 0.0 || value > 1.0) {
        throw std::invalid_argument(std::string{name} + " must be between 0 and 1");
    }
}

void validate_config(const AnatomyGateConfig& config) {
    validate_probability(config.classifier_high, "classifier_high");
    validate_probability(config.classifier_moderate, "classifier_moderate");
    validate_probability(config.segmentation_min, "segmentation_min");
    validate_probability(config.landmark_min, "landmark_min");
    validate_probability(config.minimum_margin, "minimum_margin");

    if (config.classifier_moderate > config.classifier_high) {
        throw std::invalid_argument("classifier_moderate must not exceed classifier_high");
    }
}

std::string normalize_label(std::string value) {
    const auto first = value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return {};
    }
    const auto last = value.find_last_not_of(" \t\r\n");
    return value.substr(first, last - first + 1);
}

}  // namespace

const char* anatomy_confidence_level_name(AnatomyConfidenceLevel level) noexcept {
    switch (level) {
        case AnatomyConfidenceLevel::High:
            return "high";
        case AnatomyConfidenceLevel::Moderate:
            return "moderate";
        case AnatomyConfidenceLevel::Low:
        default:
            return "low";
    }
}

AnatomyAssessment assess_anatomy(
    const std::vector<AnatomyCandidate>& candidates,
    double segmentation_confidence,
    double landmark_confidence,
    const AnatomyGateConfig& config) {
    validate_config(config);
    validate_probability(segmentation_confidence, "segmentation_confidence", true);
    validate_probability(landmark_confidence, "landmark_confidence", true);

    AnatomyAssessment assessment;
    assessment.segmentation_confidence = segmentation_confidence;
    assessment.landmark_confidence = landmark_confidence;

    if (candidates.empty()) {
        return assessment;
    }

    std::vector<AnatomyCandidate> ranked;
    ranked.reserve(candidates.size());
    std::unordered_set<std::string> seen_labels;

    for (const auto& candidate : candidates) {
        auto label = normalize_label(candidate.label);
        if (label.empty()) {
            throw std::invalid_argument("anatomy candidate label must not be empty");
        }
        validate_probability(candidate.confidence, "candidate confidence");
        if (!seen_labels.insert(label).second) {
            throw std::invalid_argument("anatomy candidate labels must be unique");
        }
        ranked.push_back({std::move(label), candidate.confidence});
    }

    std::stable_sort(
        ranked.begin(),
        ranked.end(),
        [](const AnatomyCandidate& left, const AnatomyCandidate& right) {
            return left.confidence > right.confidence;
        });

    assessment.best_label = ranked.front().label;
    assessment.classifier_confidence = ranked.front().confidence;
    assessment.runner_up_confidence = ranked.size() > 1 ? ranked[1].confidence : 0.0;
    assessment.margin = std::max(
        0.0,
        assessment.classifier_confidence - assessment.runner_up_confidence);

    const bool margin_is_sufficient = assessment.margin >= config.minimum_margin;
    if (assessment.classifier_confidence >= config.classifier_high && margin_is_sufficient) {
        assessment.level = AnatomyConfidenceLevel::High;
        assessment.anatomy_identified = true;
    } else if (
        assessment.classifier_confidence >= config.classifier_moderate &&
        margin_is_sufficient) {
        assessment.level = AnatomyConfidenceLevel::Moderate;
        assessment.anatomy_identified = true;
    }

    const bool has_segmentation = assessment.segmentation_confidence >= 0.0;
    const bool has_landmarks = assessment.landmark_confidence >= 0.0;
    const bool supporting_signals_pass =
        has_segmentation &&
        has_landmarks &&
        assessment.segmentation_confidence >= config.segmentation_min &&
        assessment.landmark_confidence >= config.landmark_min;

    assessment.organ_specific_report_allowed =
        assessment.level == AnatomyConfidenceLevel::High && supporting_signals_pass;

    if (assessment.organ_specific_report_allowed) {
        assessment.report_phrase_tr =
            "Anatomik yapı yüksek güvenle " + assessment.best_label + " ile uyumludur.";
    } else if (assessment.level == AnatomyConfidenceLevel::High) {
        assessment.report_phrase_tr =
            "En olası anatomik yapı " + assessment.best_label +
            "; segmentasyon ve anatomik landmark doğrulaması tamamlanmadan "
            "organa özgü raporlama yapılmamalıdır.";
    } else if (assessment.level == AnatomyConfidenceLevel::Moderate) {
        assessment.report_phrase_tr =
            "En olası anatomik yapı " + assessment.best_label +
            "; tek görüntüyle kesinleştirilemez.";
    }

    return assessment;
}

}  // namespace medicore::vision
