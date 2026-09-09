#include "medicore/lab/ai_dispatch.hpp"

#include <stdexcept>
#include <string>
#include <vector>

using medicore::lab::AiPatientContext;
using medicore::lab::LabRow;
using medicore::lab::ProcessedLabRow;

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

}  // namespace

int main() {
    LabRow glucose;
    glucose.raw_parameter_name = "Glucose";
    glucose.canonical_name = "Glucose";
    glucose.raw_value = "105";
    glucose.normalized_value = 105.0;
    glucose.raw_unit = "mg / dL";
    glucose.unit = "mg/dL";
    glucose.reference_min = 70.0;
    glucose.reference_max = 100.0;
    glucose.reference_text = "70-100";
    glucose.reference_type = "range";
    glucose.value_type = "numeric";
    glucose.extraction_confidence = 0.98;

    LabRow hemoglobin;
    hemoglobin.raw_parameter_name = "Hemoglobin";
    hemoglobin.canonical_name = "Hemoglobin";
    hemoglobin.raw_value = "14.3";
    hemoglobin.normalized_value = 14.3;
    hemoglobin.unit = "g/dL";
    hemoglobin.reference_min = 12.0;
    hemoglobin.reference_max = 16.0;
    hemoglobin.reference_text = "12-16";
    hemoglobin.reference_type = "range";
    hemoglobin.value_type = "numeric";
    hemoglobin.extraction_confidence = 0.99;

    const std::vector<ProcessedLabRow> processed = medicore::lab::process_rows({glucose, hemoglobin});
    require(processed.size() == 2, "Expected both laboratory rows to remain processable");
    require(processed[0].status == "HIGH", "Native Glucose safety classification should be HIGH");
    require(processed[1].status == "NORMAL", "Native Hemoglobin safety classification should be NORMAL");

    AiPatientContext patient;
    patient.age = 77;
    patient.sex = "female";

    const std::string request = medicore::lab::build_openai_lab_request(
        processed,
        patient,
        "gpt-test",
        1200
    );

    require(request.find("\"model\":\"gpt-test\"") != std::string::npos, "Model missing from request");
    require(request.find("\"max_output_tokens\":1200") != std::string::npos, "Token limit missing from request");
    require(request.find("\\\"age\\\":77") != std::string::npos, "Patient age missing from nested payload");
    require(request.find("\\\"sex\\\":\\\"female\\\"") != std::string::npos, "Patient sex missing from nested payload");
    require(request.find("\\\"test\\\":\\\"Glucose\\\"") != std::string::npos, "Glucose missing from nested payload");
    require(request.find("\\\"test\\\":\\\"Hemoglobin\\\"") != std::string::npos, "Hemoglobin missing from nested payload");
    require(request.find("\\\"value\\\":105") != std::string::npos, "Measured value missing from nested payload");
    require(request.find("\\\"reference_min\\\":70") != std::string::npos, "Reference minimum missing from nested payload");
    require(request.find("\\\"reference_max\\\":100") != std::string::npos, "Reference maximum missing from nested payload");
    require(request.find("\\\"ai_classifies_each_row\\\":true") != std::string::npos, "AI classification policy missing");

    // The deterministic native status is intentionally not sent as the model's
    // answer. The model receives values/references and classifies independently.
    require(request.find("result_status") == std::string::npos, "Native result_status leaked into AI input");
    require(request.find("\\\"status\\\":\\\"HIGH\\\"") == std::string::npos, "Native HIGH leaked into AI input");
    require(request.find("\\\"status\\\":\\\"NORMAL\\\"") == std::string::npos, "Native NORMAL leaked into AI input");

    // Request generation is always available; network dispatch depends on whether
    // libcurl support was compiled into this build.
    (void)medicore::lab::ai_http_transport_available();
    return 0;
}
