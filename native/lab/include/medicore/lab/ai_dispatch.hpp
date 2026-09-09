#pragma once

#include "medicore/lab/lab_core.hpp"

#include <optional>
#include <string>
#include <vector>

namespace medicore::lab {

inline constexpr const char* kAiDispatchContractVersion = "medicore-lab-ai-dispatch-v1";

struct AiPatientContext {
    std::optional<int> age;
    std::string sex;
};

struct AiDispatchConfig {
    std::string endpoint{"https://api.openai.com/v1/responses"};
    std::string api_key;
    std::string model;
    long timeout_ms{45000};
    int max_output_tokens{3200};
};

struct AiDispatchResult {
    long http_status{0};
    std::string model;
    std::string response_body;
};

// Build the OpenAI Responses API request that sends every processable lab row to
// the model. The native LOW/HIGH/NORMAL result is intentionally not included in
// the model input so the AI classification can be compared independently later.
std::string build_openai_lab_request(
    const std::vector<ProcessedLabRow>& rows,
    const AiPatientContext& patient,
    const std::string& model,
    int max_output_tokens = 3200
);

// Process all rows through the native normalization/validation layer, then make
// the provider HTTPS request directly from C++. Exact duplicate rows and known
// non-lab note/comment pseudo-rows remain suppressed by process_rows().
AiDispatchResult dispatch_all_lab_rows_to_ai(
    const std::vector<LabRow>& rows,
    const AiPatientContext& patient,
    const AiDispatchConfig& config
);

bool ai_http_transport_available();

}  // namespace medicore::lab
