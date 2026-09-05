#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <string>
#include <utility>
#include <vector>

#include "medicore_vision/anatomy_gate.hpp"

namespace py = pybind11;
using medicore::vision::AnatomyCandidate;
using medicore::vision::AnatomyGateConfig;
using medicore::vision::anatomy_confidence_level_name;
using medicore::vision::assess_anatomy;

PYBIND11_MODULE(medicore_anatomy, module) {
    module.doc() =
        "MediCore anatomy confidence/reporting gate for organ-classifier outputs.";
    module.attr("CONTRACT_VERSION") = medicore::vision::kAnatomyGateContract;

    module.def(
        "assess_anatomy",
        [](const std::vector<std::pair<std::string, double>>& candidates,
           double segmentation_confidence,
           double landmark_confidence,
           double classifier_high,
           double classifier_moderate,
           double segmentation_min,
           double landmark_min,
           double minimum_margin) {
            std::vector<AnatomyCandidate> native_candidates;
            native_candidates.reserve(candidates.size());
            for (const auto& [label, confidence] : candidates) {
                native_candidates.push_back({label, confidence});
            }

            const AnatomyGateConfig config{
                .classifier_high = classifier_high,
                .classifier_moderate = classifier_moderate,
                .segmentation_min = segmentation_min,
                .landmark_min = landmark_min,
                .minimum_margin = minimum_margin,
            };
            const auto result = assess_anatomy(
                native_candidates,
                segmentation_confidence,
                landmark_confidence,
                config);

            py::dict payload;
            payload["contract_version"] = medicore::vision::kAnatomyGateContract;
            payload["best_label"] = result.best_label;
            payload["classifier_confidence"] = result.classifier_confidence;
            payload["runner_up_confidence"] = result.runner_up_confidence;
            payload["margin"] = result.margin;
            payload["segmentation_confidence"] = result.segmentation_confidence;
            payload["landmark_confidence"] = result.landmark_confidence;
            payload["confidence_level"] = anatomy_confidence_level_name(result.level);
            payload["anatomy_identified"] = result.anatomy_identified;
            payload["organ_specific_report_allowed"] = result.organ_specific_report_allowed;
            payload["report_phrase_tr"] = result.report_phrase_tr;
            return payload;
        },
        py::arg("candidates"),
        py::arg("segmentation_confidence") = -1.0,
        py::arg("landmark_confidence") = -1.0,
        py::arg("classifier_high") = 0.85,
        py::arg("classifier_moderate") = 0.60,
        py::arg("segmentation_min") = 0.80,
        py::arg("landmark_min") = 0.75,
        py::arg("minimum_margin") = 0.10,
        R"doc(
Assess organ/anatomy classifier candidates and decide whether organ-specific
reporting is allowed.

A high classifier score alone is intentionally insufficient. The reporting gate
also requires segmentation and landmark verification to pass their configured
thresholds. Pass -1 for an unavailable supporting signal.
)doc");
}
