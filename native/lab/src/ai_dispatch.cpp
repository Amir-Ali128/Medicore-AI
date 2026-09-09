#include "medicore/lab/ai_dispatch.hpp"

#include <algorithm>
#include <iomanip>
#include <sstream>
#include <stdexcept>

#ifdef MEDICORE_ENABLE_AI_HTTP
#include <curl/curl.h>
#endif

namespace medicore::lab {
namespace {

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (unsigned char ch : value) {
        switch (ch) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (ch < 0x20) {
                    out << "\\u"
                        << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(ch)
                        << std::dec << std::setfill(' ');
                } else {
                    out << static_cast<char>(ch);
                }
        }
    }
    return out.str();
}

void append_json_string(std::ostringstream& out, const std::string& value) {
    out << '"' << json_escape(value) << '"';
}

void append_json_optional_number(std::ostringstream& out, const std::optional<double>& value) {
    if (!value.has_value()) {
        out << "null";
        return;
    }
    out << std::setprecision(15) << *value;
}

void append_json_optional_int(std::ostringstream& out, const std::optional<int>& value) {
    if (!value.has_value()) {
        out << "null";
        return;
    }
    out << *value;
}

std::string build_lab_input_json(
    const std::vector<ProcessedLabRow>& rows,
    const AiPatientContext& patient
) {
    std::ostringstream out;
    out << "{";
    out << "\"contract_version\":\"" << kAiDispatchContractVersion << "\",";
    out << "\"patient_context\":{";
    out << "\"age\":";
    append_json_optional_int(out, patient.age);
    out << ",\"sex\":";
    append_json_string(out, patient.sex);
    out << "},";
    out << "\"labs\":[";

    bool first = true;
    for (const ProcessedLabRow& processed : rows) {
        if (!first) {
            out << ',';
        }
        first = false;
        const LabRow& row = processed.source;
        out << '{';
        out << "\"test\":";
        append_json_string(out, processed.display_name);
        out << ",\"raw_parameter_name\":";
        append_json_string(out, row.raw_parameter_name);
        out << ",\"canonical_name\":";
        append_json_string(out, row.canonical_name);
        out << ",\"loinc_code\":";
        append_json_string(out, row.loinc_code);
        out << ",\"raw_value\":";
        append_json_string(out, row.raw_value);
        out << ",\"value\":";
        append_json_optional_number(out, row.normalized_value);
        out << ",\"raw_unit\":";
        append_json_string(out, row.raw_unit);
        out << ",\"unit\":";
        append_json_string(out, row.unit);
        out << ",\"reference_min\":";
        append_json_optional_number(out, row.reference_min);
        out << ",\"reference_max\":";
        append_json_optional_number(out, row.reference_max);
        out << ",\"reference_text\":";
        append_json_string(out, row.reference_text);
        out << ",\"reference_type\":";
        append_json_string(out, row.reference_type);
        out << ",\"value_type\":";
        append_json_string(out, row.value_type);
        out << ",\"measured_at\":";
        append_json_string(out, row.measured_at);
        out << ",\"extraction_confidence\":" << std::setprecision(6)
            << row.extraction_confidence;
        out << ",\"source_validation\":\"" << json_escape(processed.validation_status) << "\"";
        out << ",\"source_needs_review\":" << (processed.needs_review ? "true" : "false");
        out << '}';
    }

    out << "],";
    out << "\"policy\":{";
    out << "\"send_all_rows\":true,";
    out << "\"ai_classifies_each_row\":true,";
    out << "\"invent_reference_ranges\":false,";
    out << "\"physician_review_required\":true";
    out << "}";
    out << "}";
    return out.str();
}

const char* kInstructions = R"MEDICORE(
You are the laboratory clinical synthesis layer of MediCore-AI, a physician-assistive clinical decision support system.

Every laboratory row supplied in the input must be considered, including rows that appear normal and rows marked for source review. For every row, independently classify it as NORMAL, LOW, HIGH, or UNDETERMINED using only the supplied measured value and the laboratory's supplied reference information.

Hard rules:
- Do not invent, replace, or silently repair a reference range, unit, decimal point, comparator, patient fact, symptom, medication, history, or diagnosis.
- If a row cannot be reliably classified from its supplied value/reference information, return UNDETERMINED for that row.
- source_validation and source_needs_review are technical extraction/validation signals only; they are not a LOW/HIGH/NORMAL answer.
- Do not prescribe medication, doses, dose changes, or treatment. Follow-up may recommend clinician review or relevant confirmatory/monitoring tests.
- Clinical synthesis must distinguish possibilities from established diagnoses and must be traceable to the supplied laboratory evidence.
- Mention reassuring findings compactly instead of narrating every normal result in prose.
- Keep the response in Turkish except for standardized test names/codes when appropriate.
- The output is clinical decision support and requires physician review.
)MEDICORE";

const char* kStructuredOutputSchema = R"SCHEMA({
  "type":"object",
  "additionalProperties":false,
  "required":["lab_classifications","headline","overview","priority_findings","systems","reassuring_findings","priority_actions","limitations","narrative_tr"],
  "properties":{
    "lab_classifications":{
      "type":"array",
      "items":{
        "type":"object",
        "additionalProperties":false,
        "required":["test","status","reason"],
        "properties":{
          "test":{"type":"string"},
          "status":{"type":"string","enum":["NORMAL","LOW","HIGH","UNDETERMINED"]},
          "reason":{"type":"string"}
        }
      }
    },
    "headline":{"type":"string"},
    "overview":{"type":"string"},
    "priority_findings":{
      "type":"array",
      "items":{
        "type":"object",
        "additionalProperties":false,
        "required":["title","severity","summary","evidence","follow_up"],
        "properties":{
          "title":{"type":"string"},
          "severity":{"type":"string","enum":["critical","high","moderate","info"]},
          "summary":{"type":"string"},
          "evidence":{"type":"array","items":{"type":"string"}},
          "follow_up":{"type":"array","items":{"type":"string"}}
        }
      }
    },
    "systems":{
      "type":"array",
      "items":{
        "type":"object",
        "additionalProperties":false,
        "required":["title","status","summary","evidence"],
        "properties":{
          "title":{"type":"string"},
          "status":{"type":"string","enum":["attention","reassuring","mixed","uncertain"]},
          "summary":{"type":"string"},
          "evidence":{"type":"array","items":{"type":"string"}}
        }
      }
    },
    "reassuring_findings":{"type":"array","items":{"type":"string"}},
    "priority_actions":{"type":"array","items":{"type":"string"}},
    "limitations":{"type":"array","items":{"type":"string"}},
    "narrative_tr":{"type":"string"}
  }
})SCHEMA";

#ifdef MEDICORE_ENABLE_AI_HTTP
struct CurlGlobalState {
    CurlGlobalState() {
        const CURLcode code = curl_global_init(CURL_GLOBAL_DEFAULT);
        if (code != CURLE_OK) {
            throw std::runtime_error("libcurl global initialization failed");
        }
    }
    ~CurlGlobalState() {
        curl_global_cleanup();
    }
};

CurlGlobalState& curl_global_state() {
    static CurlGlobalState state;
    return state;
}

size_t write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    const size_t bytes = size * nmemb;
    auto* output = static_cast<std::string*>(userdata);
    output->append(ptr, bytes);
    return bytes;
}
#endif

}  // namespace

std::string build_openai_lab_request(
    const std::vector<ProcessedLabRow>& rows,
    const AiPatientContext& patient,
    const std::string& model,
    int max_output_tokens
) {
    if (model.empty()) {
        throw std::invalid_argument("AI model must not be empty");
    }
    if (max_output_tokens <= 0) {
        throw std::invalid_argument("max_output_tokens must be positive");
    }

    const std::string lab_input = build_lab_input_json(rows, patient);
    std::ostringstream out;
    out << '{';
    out << "\"model\":";
    append_json_string(out, model);
    out << ",\"store\":false";
    out << ",\"max_output_tokens\":" << max_output_tokens;
    out << ",\"instructions\":";
    append_json_string(out, kInstructions);
    out << ",\"text\":{\"format\":{";
    out << "\"type\":\"json_schema\",";
    out << "\"name\":\"medicore_lab_direct_ai_v1\",";
    out << "\"strict\":true,";
    out << "\"schema\":" << kStructuredOutputSchema;
    out << "}}";
    out << ",\"input\":[{";
    out << "\"role\":\"user\",";
    out << "\"content\":[{";
    out << "\"type\":\"input_text\",";
    out << "\"text\":";
    append_json_string(out, lab_input);
    out << "}]";
    out << "}]";
    out << '}';
    return out.str();
}

bool ai_http_transport_available() {
#ifdef MEDICORE_ENABLE_AI_HTTP
    return true;
#else
    return false;
#endif
}

AiDispatchResult dispatch_all_lab_rows_to_ai(
    const std::vector<LabRow>& rows,
    const AiPatientContext& patient,
    const AiDispatchConfig& config
) {
    if (rows.empty()) {
        throw std::invalid_argument("At least one laboratory row is required");
    }
    if (config.api_key.empty()) {
        throw std::invalid_argument("OpenAI API key is not configured");
    }
    if (config.model.empty()) {
        throw std::invalid_argument("AI model is not configured");
    }
    if (config.endpoint.empty()) {
        throw std::invalid_argument("AI endpoint is not configured");
    }
    if (config.timeout_ms <= 0) {
        throw std::invalid_argument("AI timeout must be positive");
    }

#ifndef MEDICORE_ENABLE_AI_HTTP
    (void)patient;
    throw std::runtime_error(
        "MediCore native lab AI HTTP transport was not compiled. "
        "Configure with -DMEDICORE_ENABLE_AI_HTTP=ON."
    );
#else
    (void)curl_global_state();
    const std::vector<ProcessedLabRow> processed = process_rows(rows);
    if (processed.empty()) {
        throw std::invalid_argument("No processable laboratory rows remain after native validation");
    }
    const std::string request_body = build_openai_lab_request(
        processed,
        patient,
        config.model,
        config.max_output_tokens
    );

    CURL* curl = curl_easy_init();
    if (curl == nullptr) {
        throw std::runtime_error("Could not initialize native AI HTTP request");
    }

    std::string response_body;
    struct curl_slist* headers = nullptr;
    const std::string authorization = "Authorization: Bearer " + config.api_key;
    headers = curl_slist_append(headers, "Content-Type: application/json");
    headers = curl_slist_append(headers, authorization.c_str());

    curl_easy_setopt(curl, CURLOPT_URL, config.endpoint.c_str());
    curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    curl_easy_setopt(curl, CURLOPT_POST, 1L);
    curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request_body.c_str());
    curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(request_body.size()));
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_body);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, config.timeout_ms);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, std::min<long>(config.timeout_ms, 10000L));
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, "MediCore-Native-Lab/1.0");

    const CURLcode code = curl_easy_perform(curl);
    long http_status = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_status);

    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);

    if (code != CURLE_OK) {
        throw std::runtime_error(
            std::string("Native AI HTTP request failed: ") + curl_easy_strerror(code)
        );
    }
    if (http_status < 200 || http_status >= 300) {
        throw std::runtime_error(
            "Native AI provider returned HTTP status " + std::to_string(http_status)
        );
    }

    AiDispatchResult result;
    result.http_status = http_status;
    result.model = config.model;
    result.response_body = std::move(response_body);
    return result;
#endif
}

}  // namespace medicore::lab
