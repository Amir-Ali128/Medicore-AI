#include "medicore/lab/lab_core.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <unordered_map>
#include <utility>

namespace medicore::lab {
namespace {

std::string lower_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

bool finite_optional(const std::optional<double>& value) {
    return !value.has_value() || std::isfinite(*value);
}

std::string make_dedupe_key(const LabRow& row) {
    std::string name = row.canonical_name.empty() ? row.raw_parameter_name : row.canonical_name;
    name = lower_ascii(normalize_whitespace(name));
    const std::string unit = lower_ascii(normalize_unit(row.unit));
    return name + "\x1f" + unit + "\x1f" + normalize_whitespace(row.measured_at);
}

}  // namespace

std::string normalize_whitespace(const std::string& value) {
    std::ostringstream out;
    bool pending_space = false;
    bool wrote_any = false;

    for (unsigned char ch : value) {
        if (std::isspace(ch)) {
            if (wrote_any) {
                pending_space = true;
            }
            continue;
        }
        if (pending_space) {
            out << ' ';
            pending_space = false;
        }
        out << static_cast<char>(ch);
        wrote_any = true;
    }
    return out.str();
}

std::string normalize_unit(const std::string& value) {
    std::string result = normalize_whitespace(value);

    // Keep the laboratory's original unit semantics while removing common
    // presentation-only whitespace differences that otherwise create duplicate rows.
    const std::pair<const char*, const char*> replacements[] = {
        {"mg / dL", "mg/dL"},
        {"g / dL", "g/dL"},
        {"K / mm3", "K/mm3"},
        {"M / mm3", "M/mm3"},
        {"mL / dk / 1.73m2", "mL/dk/1.73m2"},
        {"uIU / mL", "uIU/mL"},
    };
    for (const auto& [from, to] : replacements) {
        std::size_t pos = 0;
        while ((pos = result.find(from, pos)) != std::string::npos) {
            result.replace(pos, std::char_traits<char>::length(from), to);
            pos += std::char_traits<char>::length(to);
        }
    }
    return result;
}

double clamp_confidence(double value) {
    if (!std::isfinite(value)) {
        return 0.0;
    }
    return std::clamp(value, 0.0, 1.0);
}

ProcessedLabRow process_row(const LabRow& input) {
    ProcessedLabRow out;
    out.source = input;
    out.source.raw_parameter_name = normalize_whitespace(input.raw_parameter_name);
    out.source.canonical_name = normalize_whitespace(input.canonical_name);
    out.source.raw_value = normalize_whitespace(input.raw_value);
    out.source.unit = normalize_unit(input.unit);
    out.source.reference_text = normalize_whitespace(input.reference_text);
    out.source.measured_at = normalize_whitespace(input.measured_at);
    out.source.extraction_confidence = clamp_confidence(input.extraction_confidence);

    out.display_name = out.source.canonical_name.empty()
        ? out.source.raw_parameter_name
        : out.source.canonical_name;

    if (out.display_name.empty() || out.display_name.size() > 255) {
        out.status = "NEEDS_REVIEW";
        out.needs_review = true;
        out.reason = "Laboratuvar parametre adı eksik veya geçersiz.";
        out.rule_applied = "native_invalid_parameter_name";
        return out;
    }

    if (!finite_optional(out.source.normalized_value) ||
        !finite_optional(out.source.reference_min) ||
        !finite_optional(out.source.reference_max)) {
        out.status = "NEEDS_REVIEW";
        out.needs_review = true;
        out.reason = "Sayısal alanlardan en az biri sonlu bir sayı değil.";
        out.rule_applied = "native_non_finite_numeric";
        return out;
    }

    if (!out.source.normalized_value.has_value()) {
        out.status = "NEEDS_REVIEW";
        out.needs_review = true;
        out.reason = "Sayısal sonuç güvenilir biçimde çıkarılamadı; hekim kontrolü gerekir.";
        out.rule_applied = "native_missing_numeric_value";
        return out;
    }

    if (out.source.reference_min && out.source.reference_max &&
        *out.source.reference_min > *out.source.reference_max) {
        out.status = "NEEDS_REVIEW";
        out.needs_review = true;
        out.reason = "Referans alt sınırı üst sınırdan büyük; kaynak rapor kontrol edilmelidir.";
        out.rule_applied = "native_invalid_reference_range";
        return out;
    }

    const double value = *out.source.normalized_value;
    if (out.source.reference_min && value < *out.source.reference_min) {
        out.status = "LOW";
        out.reason = "Değer kaynak rapordaki referans alt sınırının altında.";
        out.rule_applied = "native_value_below_min";
        out.classification_confidence = out.source.extraction_confidence;
    } else if (out.source.reference_max && value > *out.source.reference_max) {
        out.status = "HIGH";
        out.reason = "Değer kaynak rapordaki referans üst sınırının üzerinde.";
        out.rule_applied = "native_value_above_max";
        out.classification_confidence = out.source.extraction_confidence;
    } else if (out.source.reference_min || out.source.reference_max) {
        out.status = "NORMAL";
        out.reason = "Değer kaynak rapordaki mevcut referans sınırları içinde.";
        out.rule_applied = "native_value_within_reference";
        out.classification_confidence = out.source.extraction_confidence;
    } else {
        out.status = "NEEDS_REVIEW";
        out.needs_review = true;
        out.reason = "Kaynak raporda güvenilir referans sınırı bulunamadı.";
        out.rule_applied = "native_missing_reference";
        return out;
    }

    // AI explicitly marks ambiguous visual/text extraction. Deterministic numeric
    // classification is preserved, but the row is still routed for human review.
    if (out.source.ai_needs_review || out.source.extraction_confidence < 0.85) {
        out.needs_review = true;
        out.classification_confidence = std::min(out.classification_confidence, 0.84);
        if (out.source.ai_needs_review) {
            out.reason += " Astra çıkarımı bu satır için ayrıca doğrulama işareti taşıyor.";
        } else {
            out.reason += " Çıkarım güveni %85 eşiğinin altında.";
        }
    }

    return out;
}

std::vector<ProcessedLabRow> process_rows(const std::vector<LabRow>& rows) {
    std::vector<ProcessedLabRow> output;
    output.reserve(rows.size());

    // Exact duplicate rows from repeated PDF headers/pages are collapsed. When the
    // same test/date/unit appears more than once, keep the highest-confidence copy.
    std::unordered_map<std::string, std::size_t> index_by_key;
    for (const LabRow& row : rows) {
        ProcessedLabRow processed = process_row(row);
        const std::string key = make_dedupe_key(processed.source);

        auto found = index_by_key.find(key);
        if (key.empty() || found == index_by_key.end()) {
            index_by_key.emplace(key, output.size());
            output.push_back(std::move(processed));
            continue;
        }

        ProcessedLabRow& existing = output[found->second];
        if (processed.source.extraction_confidence > existing.source.extraction_confidence) {
            existing = std::move(processed);
        }
    }
    return output;
}

}  // namespace medicore::lab
