#include <cassert>
#include <stdexcept>
#include <vector>

#include "medicore_vision/anatomy_gate.hpp"

using medicore::vision::AnatomyCandidate;
using medicore::vision::AnatomyConfidenceLevel;
using medicore::vision::assess_anatomy;

int main() {
    {
        const auto result = assess_anatomy({
            {"SPLEEN", 0.55},
            {"STOMACH", 0.45},
        });
        assert(result.level == AnatomyConfidenceLevel::Low);
        assert(!result.anatomy_identified);
        assert(!result.organ_specific_report_allowed);
    }

    {
        const auto result = assess_anatomy({
            {"SPLEEN", 0.93},
            {"STOMACH", 0.04},
            {"LEFT_KIDNEY", 0.03},
        });
        assert(result.level == AnatomyConfidenceLevel::High);
        assert(result.anatomy_identified);
        assert(!result.organ_specific_report_allowed);
    }

    {
        const auto result = assess_anatomy(
            {
                {"SPLEEN", 0.93},
                {"STOMACH", 0.04},
                {"LEFT_KIDNEY", 0.03},
            },
            0.91,
            0.82);
        assert(result.level == AnatomyConfidenceLevel::High);
        assert(result.anatomy_identified);
        assert(result.organ_specific_report_allowed);
        assert(result.best_label == "SPLEEN");
    }

    {
        const auto result = assess_anatomy(
            {
                {"SPLEEN", 0.90},
                {"STOMACH", 0.85},
            },
            0.95,
            0.95);
        assert(result.level == AnatomyConfidenceLevel::Low);
        assert(!result.anatomy_identified);
        assert(!result.organ_specific_report_allowed);
    }

    {
        bool threw = false;
        try {
            (void)assess_anatomy({{"SPLEEN", 1.2}});
        } catch (const std::invalid_argument&) {
            threw = true;
        }
        assert(threw);
    }

    return 0;
}
