#include "medicore/lab/lab_core.hpp"

#include <cassert>
#include <vector>

using medicore::lab::LabRow;
using medicore::lab::process_row;
using medicore::lab::process_rows;

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
    }

    {
        LabRow row;
        row.raw_parameter_name = "CRP";
        row.normalized_value = 2.1;
        row.unit = "mg/L";
        row.extraction_confidence = 0.99;
        const auto result = process_row(row);
        assert(result.status == "NEEDS_REVIEW");
        assert(result.needs_review);
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

    return 0;
}
