#include "medicore/lab/clinical_metrics.hpp"
#include "medicore/lab/lab_core.hpp"

#include <cassert>
#include <cmath>
#include <string>
#include <vector>

using medicore::lab::LabRow;
using medicore::lab::compute_derived_metrics;
using medicore::lab::process_row;
using medicore::lab::process_rows;

namespace {

const medicore::lab::DerivedMetric* find_metric(
    const std::vector<medicore::lab::DerivedMetric>& metrics,
    const std::string& code
) {
    for (const auto& metric : metrics) {
        if (metric.code == code) {
            return &metric;
        }
    }
    return nullptr;
}

LabRow numeric_row(
    const std::string& name,
    double value,
    const std::string& unit,
    double confidence = 0.99
) {
    LabRow row;
    row.raw_parameter_name = name;
    row.canonical_name = name;
    row.normalized_value = value;
    row.unit = unit;
    row.extraction_confidence = confidence;
    return row;
}

}  // namespace

int main() {
    {
        LabRow row;
        row.raw_parameter_name = " HbA1c ";
        row.normalized_value = 9.4;
        row.unit = "%";
        row.reference_max = 6.5;
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.status == "HIGH");
        assert(result.validation_status == "VALID");
        assert(!result.needs_review);
        assert(result.rule_applied == "native_value_above_max");
    }

    {
        LabRow row;
        row.raw_parameter_name = "Vitamin D";
        row.normalized_value = 24.3;
        row.unit = "ng/mL";
        row.reference_min = 30.0;
        row.reference_max = 80.0;
        row.extraction_confidence = 0.98;
        const auto result = process_row(row);
        assert(result.status == "LOW");
        assert(result.validation_status == "VALID");
    }

    // Strict upper bound: <5 means 5 itself is outside the reference condition.
    {
        LabRow row;
        row.raw_parameter_name = "CRP";
        row.normalized_value = 5.0;
        row.unit = "mg/L";
        row.reference_max = 5.0;
        row.reference_text = "< 5";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.source.reference_type == "less_than");
        assert(result.status == "HIGH");
        assert(result.validation_status == "VALID");
    }

    // Inclusive upper bound: <=5 keeps equality inside the reference condition.
    {
        LabRow row;
        row.raw_parameter_name = "Marker A";
        row.normalized_value = 5.0;
        row.reference_max = 5.0;
        row.reference_text = "<= 5";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.source.reference_type == "less_equal");
        assert(result.status == "NORMAL");
    }

    // Strict lower bound: >40 means 40 itself does not satisfy the condition.
    {
        LabRow row;
        row.raw_parameter_name = "HDL";
        row.normalized_value = 40.0;
        row.unit = "mg/dL";
        row.reference_min = 40.0;
        row.reference_text = "> 40";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.source.reference_type == "greater_than");
        assert(result.status == "LOW");
    }

    // Inclusive lower bound: >=40 keeps equality inside the reference condition.
    {
        LabRow row;
        row.raw_parameter_name = "Marker B";
        row.normalized_value = 40.0;
        row.reference_min = 40.0;
        row.reference_text = ">= 40";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.source.reference_type == "greater_equal");
        assert(result.status == "NORMAL");
    }

    // A lone numeric max without comparator text preserves legacy inclusive behavior.
    {
        LabRow row;
        row.raw_parameter_name = "Marker C";
        row.normalized_value = 5.0;
        row.reference_max = 5.0;
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.source.reference_type == "range");
        assert(result.status == "NORMAL");
    }

    {
        LabRow row;
        row.raw_parameter_name = "CRP";
        row.normalized_value = 2.1;
        row.unit = "mg/L";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.status == "NEEDS_REVIEW");
        assert(result.validation_status == "NEEDS_REVIEW");
        assert(result.needs_review);
    }

    // Invalid range is structurally invalid, not silently reinterpreted.
    {
        LabRow row;
        row.raw_parameter_name = "Broken Range";
        row.normalized_value = 50.0;
        row.reference_min = 100.0;
        row.reference_max = 70.0;
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.status == "NEEDS_REVIEW");
        assert(result.validation_status == "INVALID");
        assert(result.needs_review);
    }

    // Comparator with a missing required bound cannot be classified safely.
    {
        LabRow row;
        row.raw_parameter_name = "Malformed Reference";
        row.normalized_value = 2.0;
        row.reference_type = "less_than";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.status == "NEEDS_REVIEW");
        assert(result.validation_status == "NEEDS_REVIEW");
        assert(result.rule_applied == "native_reference_shape_mismatch");
    }

    // Low extraction confidence keeps the numeric classification but downgrades trust.
    {
        LabRow row;
        row.raw_parameter_name = "Glucose";
        row.normalized_value = 180.0;
        row.reference_max = 100.0;
        row.extraction_confidence = 0.70;
        const auto result = process_row(row);
        assert(result.status == "HIGH");
        assert(result.validation_status == "WARNING");
        assert(result.needs_review);
        assert(result.classification_confidence <= 0.84);
    }

    {
        LabRow first;
        first.raw_parameter_name = "Glukoz";
        first.normalized_value = 198.0;
        first.unit = "mg/dL";
        first.reference_max = 100.0;
        first.measured_at = "2026-09-06";
        first.extraction_confidence = 0.70;

        LabRow second = first;
        second.extraction_confidence = 0.98;

        const auto results = process_rows({first, second});
        assert(results.size() == 1);
        assert(results.front().source.extraction_confidence == 0.98);
        assert(results.front().status == "HIGH");
        assert(results.front().validation_status == "VALID");
    }

    // Same value/range but different comparator semantics must not be deduplicated.
    {
        LabRow strict;
        strict.raw_parameter_name = "Boundary Test";
        strict.normalized_value = 5.0;
        strict.reference_max = 5.0;
        strict.reference_text = "<5";
        strict.extraction_confidence = 0.99;

        LabRow inclusive = strict;
        inclusive.reference_text = "<=5";

        const auto results = process_rows({strict, inclusive});
        assert(results.size() == 2);
    }

    {
        LabRow note;
        note.raw_parameter_name = "Note";
        note.raw_value = "sample note text";

        LabRow hba1c;
        hba1c.raw_parameter_name = "HbA1c";
        hba1c.normalized_value = 9.4;
        hba1c.reference_max = 6.5;
        hba1c.unit = "%";
        hba1c.extraction_confidence = 0.99;

        const auto results = process_rows({note, hba1c});
        assert(results.size() == 1);
        assert(results.front().display_name == "HbA1c");
        assert(results.front().status == "HIGH");
    }

    {
        auto creatinine = numeric_row("Creatinine", 1.3, "mg/dL");
        auto hba1c = numeric_row("HbA1c", 9.4, "%");
        auto total = numeric_row("Total Cholesterol", 231.0, "mg/dL");
        auto hdl = numeric_row("HDL", 50.0, "mg/dL");
        auto ast = numeric_row("AST", 15.0, "U/L");
        auto alt = numeric_row("ALT", 11.0, "U/L");
        auto platelets = numeric_row("Platelets", 250.0, "10^9/L");

        const auto rows = process_rows({creatinine, hba1c, total, hdl, ast, alt, platelets});
        const auto metrics = compute_derived_metrics(rows, 77, "female");

        const auto* egfr = find_metric(metrics, "egfr_ckd_epi_2021");
        assert(egfr != nullptr);
        assert(egfr->value > 42.0 && egfr->value < 43.0);

        const auto* eag = find_metric(metrics, "estimated_average_glucose");
        assert(eag != nullptr);
        assert(std::abs(eag->value - 223.08) < 0.01);

        const auto* non_hdl = find_metric(metrics, "non_hdl_cholesterol");
        assert(non_hdl != nullptr);
        assert(std::abs(non_hdl->value - 181.0) < 0.001);

        const auto* fib4 = find_metric(metrics, "fib4");
        assert(fib4 != nullptr);
        assert(fib4->value > 1.39 && fib4->value < 1.40);
        assert(fib4->note.find("Age over 65") != std::string::npos);
    }

    {
        auto creatinine = numeric_row("Creatinine", 1.3, "mg/dL");
        const auto rows = process_rows({creatinine});
        const auto metrics = compute_derived_metrics(rows, 77, "unknown");
        assert(find_metric(metrics, "egfr_ckd_epi_2021") == nullptr);
    }

    return 0;
}
