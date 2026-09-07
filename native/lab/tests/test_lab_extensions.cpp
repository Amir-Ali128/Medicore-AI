#include "medicore/lab/lab_extensions.hpp"

#include <cassert>
#include <cmath>
#include <iostream>
#include <vector>

using namespace medicore::lab;

namespace {

bool close_to(double a, double b, double eps = 1e-3) {
    return std::abs(a - b) <= eps;
}

void test_reference_parser() {
    {
        const auto parsed = parse_reference_text("< 5 mg/L");
        assert(parsed.parsed);
        assert(parsed.type == "less_than");
        assert(parsed.maximum && close_to(*parsed.maximum, 5.0));
        assert(!parsed.minimum);
    }
    {
        const auto parsed = parse_reference_text("≤ 5");
        assert(parsed.parsed);
        assert(parsed.type == "less_equal");
        assert(parsed.maximum && close_to(*parsed.maximum, 5.0));
    }
    {
        const auto parsed = parse_reference_text(">= 40");
        assert(parsed.parsed);
        assert(parsed.type == "greater_equal");
        assert(parsed.minimum && close_to(*parsed.minimum, 40.0));
    }
    {
        const auto parsed = parse_reference_text("3,5 - 5,1 mmol/L");
        assert(parsed.parsed);
        assert(parsed.type == "range");
        assert(parsed.minimum && close_to(*parsed.minimum, 3.5));
        assert(parsed.maximum && close_to(*parsed.maximum, 5.1));
    }
    {
        const auto parsed = parse_reference_text("Negative");
        assert(parsed.parsed);
        assert(parsed.type == "qualitative");
        assert(parsed.qualitative_value == "negative");
    }
    {
        const auto parsed = parse_reference_text("1:80");
        assert(parsed.parsed);
        assert(parsed.titer_numerator && *parsed.titer_numerator == 1);
        assert(parsed.titer_denominator && *parsed.titer_denominator == 80);
    }
    {
        const auto parsed = parse_reference_text("9 - 2");
        assert(!parsed.parsed);
        assert(parsed.needs_review);
    }
}

void test_unit_conversion() {
    {
        const auto result = convert_lab_value("glucose", 100.0, "mg/dL", "mmol/L");
        assert(result.supported && result.converted && result.value);
        assert(close_to(*result.value, 5.55, 1e-2));
    }
    {
        const auto result = convert_lab_value("creatinine", 1.0, "mg/dL", "µmol/L");
        assert(result.supported && result.value);
        assert(close_to(*result.value, 88.4, 1e-2));
    }
    {
        const auto result = convert_lab_value("HbA1c", 7.0, "%", "mmol/mol");
        assert(result.supported && result.value);
        assert(*result.value > 52.0 && *result.value < 54.0);
    }
    {
        const auto result = convert_lab_value("unknown", 10.0, "mg/dL", "mmol/L");
        assert(!result.supported);
        assert(result.value && close_to(*result.value, 10.0));
    }
}

void test_plausibility() {
    {
        const auto result = validate_plausibility("potassium", 71.0, "mmol/L");
        assert(result.status == "WARNING");
        assert(result.needs_review);
    }
    {
        const auto result = validate_plausibility("glucose", -1.0, "mg/dL");
        assert(result.status == "INVALID");
        assert(result.needs_review);
    }
    {
        const auto result = validate_plausibility("sodium", 140.0, "mmol/L");
        assert(result.status == "VALID");
        assert(!result.needs_review);
    }
}

void test_fractional_age_reference_selector() {
    std::vector<ReferenceCandidateV2> candidates;

    ReferenceCandidateV2 neonatal;
    neonatal.reference_min = 1.0;
    neonatal.reference_max = 2.0;
    neonatal.unit = "mg/dL";
    neonatal.age_min_years = 0.0;
    neonatal.age_max_years = 0.10;
    candidates.push_back(neonatal);

    ReferenceCandidateV2 infant;
    infant.reference_min = 2.0;
    infant.reference_max = 3.0;
    infant.unit = "mg/dL";
    infant.age_min_years = 0.10;
    infant.age_max_years = 1.0;
    candidates.push_back(infant);

    const auto neonatal_selection = select_reference_candidate_v2(candidates, "", 0.05, std::nullopt);
    assert(neonatal_selection.index && *neonatal_selection.index == 0);
    assert(!neonatal_selection.needs_review);

    const auto infant_selection = select_reference_candidate_v2(candidates, "", 0.5, std::nullopt);
    assert(infant_selection.index && *infant_selection.index == 1);
    assert(!infant_selection.needs_review);
}

}  // namespace

int main() {
    test_reference_parser();
    test_unit_conversion();
    test_plausibility();
    test_fractional_age_reference_selector();
    std::cout << "lab extensions tests passed\n";
    return 0;
}
