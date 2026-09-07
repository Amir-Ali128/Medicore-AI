#include "medicore/lab/deterministic_core.hpp"

#include <cassert>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

int main() {
    using namespace medicore::lab;

    assert(normalize_alias(" İnsülin ") == "insulin");
    assert(normalize_alias("Nötrofil %") == "notrofil");
    assert(alias_similarity_ratio("Triglyceride", "Triglycerides") > 0.90);
    assert(alias_similarity_ratio("Vitamin B1", "Vitamin B12") < 1.0);

    {
        const auto result = evaluate_rule(true, false, false, 5.0, 1.0, 5.0);
        assert(result.status == "NORMAL");
        assert(!result.needs_review);
    }
    {
        const auto result = evaluate_rule(true, false, false, 6.0, 1.0, 5.0);
        assert(result.status == "HIGH");
    }
    {
        const auto result = compare_trend(105.0, 100.0, 30);
        assert(result.status == "STABLE");
        assert(result.time_difference_days == 30);
    }
    {
        const auto result = compare_trend(120.0, 100.0, std::nullopt);
        assert(result.status == "UP");
        assert(result.percentage_difference.has_value());
        assert(std::abs(*result.percentage_difference - 20.0) < 1e-9);
    }
    {
        ReferenceCandidate male;
        male.reference_min = 13.0;
        male.reference_max = 17.0;
        male.unit = "g/dL";
        male.sex = "MALE";

        ReferenceCandidate female;
        female.reference_min = 12.0;
        female.reference_max = 16.0;
        female.unit = "g/dL";
        female.sex = "FEMALE";

        const std::vector<ReferenceCandidate> candidates{male, female};
        const auto selection = select_reference_candidate(candidates, "MALE", 30, std::nullopt);
        assert(selection.index.has_value());
        assert(*selection.index == 0);
        assert(selection.strategy == "database_demographic");
        assert(!selection.needs_review);
    }
    {
        ReferenceCandidate adult;
        adult.reference_min = 1.0;
        adult.reference_max = 2.0;
        adult.unit = "x";
        adult.age_min = 18;

        const auto selection = select_reference_candidate({adult}, "", std::nullopt, std::nullopt);
        assert(!selection.index.has_value());
        assert(selection.needs_review);
    }

    return 0;
}
