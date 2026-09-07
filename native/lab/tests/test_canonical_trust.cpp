#include "medicore/lab/lab_core.hpp"

#include <cassert>
#include <string>

using medicore::lab::LabRow;
using medicore::lab::process_row;
using medicore::lab::process_rows;

int main() {
    {
        LabRow row;
        row.canonical_row_contract = medicore::lab::kCanonicalRowContractVersion;
        row.raw_parameter_name = "Glucose";
        row.canonical_name = "Glucose";
        row.raw_value = "105";
        row.normalized_value = 105.0;
        row.raw_unit = "mg/dL";
        row.unit = "mg/dL";
        row.reference_min = 70.0;
        row.reference_max = 100.0;
        row.extraction_confidence = 0.98;
        row.source_type = "enabiz_pdf";
        row.source_file_name = "report.pdf";
        row.source_page = 2;
        row.source_sha256 = "abc123";
        row.source_record_id = "report-42";
        row.integration_type = "";
        row.ingestion_reasons = {"source_verified"};

        const auto result = process_row(row);
        assert(result.status == "HIGH");
        assert(result.validation_status == "VALID");
        assert(!result.needs_review);
        assert(result.source.canonical_row_contract == medicore::lab::kCanonicalRowContractVersion);
        assert(result.source.raw_unit == "mg/dL");
        assert(result.source.source_type == "enabiz_pdf");
        assert(result.source.source_file_name == "report.pdf");
        assert(result.source.source_page.has_value() && *result.source.source_page == 2);
        assert(result.source.source_sha256 == "abc123");
        assert(result.source.source_record_id == "report-42");
        assert(result.source.ingestion_reasons.size() == 1);
    }

    // Dedupe must keep provenance from the highest-confidence source row.
    {
        LabRow low;
        low.canonical_row_contract = medicore::lab::kCanonicalRowContractVersion;
        low.raw_parameter_name = "Potassium";
        low.normalized_value = 4.4;
        low.unit = "mmol/L";
        low.reference_min = 3.5;
        low.reference_max = 5.1;
        low.measured_at = "2026-09-08";
        low.extraction_confidence = 0.70;
        low.source_type = "screenshot";
        low.source_file_name = "screen.png";
        low.source_sha256 = "low-hash";

        LabRow high = low;
        high.extraction_confidence = 0.99;
        high.source_type = "enabiz_pdf";
        high.source_file_name = "source.pdf";
        high.source_sha256 = "high-hash";

        const auto results = process_rows({low, high});
        assert(results.size() == 1);
        assert(results.front().source.extraction_confidence == 0.99);
        assert(results.front().source.source_type == "enabiz_pdf");
        assert(results.front().source.source_file_name == "source.pdf");
        assert(results.front().source.source_sha256 == "high-hash");
        assert(results.front().validation_status == "VALID");
    }

    // Low-confidence canonical input remains classified but is never AI-trusted.
    {
        LabRow row;
        row.canonical_row_contract = medicore::lab::kCanonicalRowContractVersion;
        row.raw_parameter_name = "Potassium";
        row.normalized_value = 71.0;
        row.unit = "mmol/L";
        row.reference_min = 3.5;
        row.reference_max = 5.1;
        row.extraction_confidence = 0.40;
        row.ai_needs_review = true;

        const auto result = process_row(row);
        assert(result.status == "HIGH");
        assert(result.validation_status == "WARNING");
        assert(result.needs_review);
        assert(result.classification_confidence <= 0.84);
    }

    return 0;
}
