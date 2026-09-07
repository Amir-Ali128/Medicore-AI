#include "medicore/lab/lab_core.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
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

std::string numeric_key(const std::optional<double>& value) {
    if (!value) {
        return "null";
    }
    std::ostringstream out;
    out.precision(15);
    out << *value;
    return out.str();
}

bool starts_with(const std::string& value, const std::string& prefix) {
    return value.size() >= prefix.size() && value.compare(0, prefix.size(), prefix) == 0;
}

std::string infer_reference_type(const LabRow& row) {
    const std::string explicit_type = normalize_reference_type(row.reference_type);
    if (!explicit_type.empty() && explicit_type != "unknown") {
        return explicit_type;
    }

    const std::string text = normalize_whitespace(row.reference_text);
    if (starts_with(text, "<=" ) || starts_with(text, "≤")) {
        return "less_equal";
    }
    if (starts_with(text, "<")) {
        return "less_than";
    }
    if (starts_with(text, ">=") || starts_with(text, "≥")) {
        return "greater_equal";
    }
    if (starts_with(text, ">")) {
        return "greater_than";
    }

    // A plain min/max supplied by the laboratory is treated as an inclusive range.
    // With only one bound and no comparator text we intentionally preserve the
    // legacy inclusive-bound behavior instead of guessing a strict inequality.
    if (row.reference_min || row.reference_max) {
        return "range";
    }
    if (!text.empty()) {
        return "qualitative";
    }
    return "unknown";
}

bool reference_shape_is_valid(const LabRow& row, const std::string& type) {
    if (type == "less_than" || type == "less_equal") {
        return row.reference_max.has_value();
    }
    if (type == "greater_than" || type == "greater_equal") {
        return row.reference_min.has_value();
    }
    if (type == "range") {
        return row.reference_min.has_value() || row.reference_max.has_value();
    }
    return true;
}

std::string make_dedupe_key(const LabRow& row) {
    std::string name = row.canonical_name.empty() ? row.raw_parameter_name : row.canonical_name;
    name = lower_ascii(normalize_whitespace(name));
    const std::string unit = lower_ascii(normalize_unit(row.unit));
    const std::string reference_type = infer_reference_type(row);
    return name + "\x1f" + unit + "\x1f" + normalize_whitespace(row.measured_at) +
        "\x1f" + numeric_key(row.normalized_value) +
        "\x1f" + numeric_key(row.reference_min) +
        "\x1f" + numeric_key(row.reference_max) +
        "\x1f" + reference_type;
}

bool is_pseudo_parameter(const LabRow& row) {
    std::string name = row.canonical_name.empty() ? row.raw_parameter_name : row.canonical_name;
    name = lower_ascii(normalize_whitespace(name));

    static const std::unordered_set<std::string> kPseudoNames = {
        "note",
        "notes",
        "not",
        "comment",
        "comments",
        "remark",
        "remarks",
        "aciklama",
        "açıklama",
    };
    return kPseudoNames.contains(name);
}

void mark_unclassifiable(
    ProcessedLabRow& out,
    const std::string& validation_status,
    const std::string& reason,
    const std::string& rule
) {
    out.status = "NEEDS_REVIEW";
    out.validation_status = validation_status;
    out.needs_review = true;
    out.reason = reason;
    out.rule_applied = rule;
    out.classification_confidence = 0.0;
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

std::string normalize_reference_type(const std::string& value) {
    std::string normalized = lower_ascii(normalize_whitespace(value));
    std::replace(normalized.begin(), normalized.end(), '-', '_');
    std::replace(normalized.begin(), normalized.end(), ' ', '_');

    if (normalized.empty()) {
        return {};
    }
    if (normalized == "range" || normalized == "between" || normalized == "interval") {
        return "range";
    }
    if (normalized == "less_than" || normalized == "lt" || normalized == "<") {
        return "less_than";
    }
    if (normalized == "less_equal" || normalized == "less_than_or_equal" ||
        normalized == "lte" || normalized == "<=") {
        return "less_equal";
    }
    if (normalized == "greater_than" || normalized == "gt" || normalized == ">") {
        return "greater_than";
    }
    if (normalized == "greater_equal" || normalized == "greater_than_or_equal" ||
        normalized == "gte" || normalized == ">=") {
        return "greater_equal";
    }
    if (normalized == "qualitative" || normalized == "text") {
        return "qualitative";
    }
    return "unknown";
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
    out.source.loinc_code = normalize_whitespace(input.loinc_code);
    out.source.raw_value = normalize_whitespace(input.raw_value);
    out.source.unit = normalize_unit(input.unit);
    out.source.reference_text = normalize_whitespace(input.reference_text);
    out.source.reference_type = infer_reference_type(out.source);
    out.source.measured_at = normalize_whitespace(input.measured_at);
    out.source.source_file_name = normalize_whitespace(input.source_file_name);
    out.source.extraction_confidence = clamp_confidence(input.extraction_confidence);

    out.display_name = out.source.canonical_name.empty()
        ? out.source.raw_parameter_name
        : out.source.canonical_name;

    if (out.display_name.empty() || out.display_name.size() > 255) {
        mark_unclassifiable(
            out,
            "INVALID",
            "Laboratuvar parametre adı eksik veya geçersiz.",
            "native_invalid_parameter_name"
        );
        return out;
    }

    if (!finite_optional(out.source.normalized_value) ||
        !finite_optional(out.source.reference_min) ||
        !finite_optional(out.source.reference_max)) {
        mark_unclassifiable(
            out,
            "INVALID",
            "Sayısal alanlardan en az biri sonlu bir sayı değil.",
            "native_non_finite_numeric"
        );
        return out;
    }

    if (!out.source.normalized_value.has_value()) {
        mark_unclassifiable(
            out,
            "NEEDS_REVIEW",
            "Sayısal sonuç güvenilir biçimde çıkarılamadı; kaynak belge kontrolü gerekir.",
            "native_missing_numeric_value"
        );
        return out;
    }

    if (out.source.reference_min && out.source.reference_max &&
        *out.source.reference_min > *out.source.reference_max) {
        mark_unclassifiable(
            out,
            "INVALID",
            "Referans alt sınırı üst sınırdan büyük; kaynak rapor kontrol edilmelidir.",
            "native_invalid_reference_range"
        );
        return out;
    }

    if (!reference_shape_is_valid(out.source, out.source.reference_type)) {
        mark_unclassifiable(
            out,
            "NEEDS_REVIEW",
            "Referans karşılaştırma türü için gerekli sınır değeri eksik.",
            "native_reference_shape_mismatch"
        );
        return out;
    }

    const double value = *out.source.normalized_value;
    const std::string& type = out.source.reference_type;

    if (type == "less_than") {
        if (value >= *out.source.reference_max) {
            out.status = "HIGH";
            out.reason = "Değer kaynak rapordaki sıkı üst sınırın (<) dışında.";
            out.rule_applied = "native_value_not_less_than_max";
        } else {
            out.status = "NORMAL";
            out.reason = "Değer kaynak rapordaki sıkı üst sınır (<) koşulunu sağlıyor.";
            out.rule_applied = "native_value_less_than_max";
        }
    } else if (type == "less_equal") {
        if (value > *out.source.reference_max) {
            out.status = "HIGH";
            out.reason = "Değer kaynak rapordaki üst sınırın (≤) üzerinde.";
            out.rule_applied = "native_value_above_less_equal_max";
        } else {
            out.status = "NORMAL";
            out.reason = "Değer kaynak rapordaki üst sınır (≤) koşulunu sağlıyor.";
            out.rule_applied = "native_value_within_less_equal_max";
        }
    } else if (type == "greater_than") {
        if (value <= *out.source.reference_min) {
            out.status = "LOW";
            out.reason = "Değer kaynak rapordaki sıkı alt sınırın (>) dışında.";
            out.rule_applied = "native_value_not_greater_than_min";
        } else {
            out.status = "NORMAL";
            out.reason = "Değer kaynak rapordaki sıkı alt sınır (>) koşulunu sağlıyor.";
            out.rule_applied = "native_value_greater_than_min";
        }
    } else if (type == "greater_equal") {
        if (value < *out.source.reference_min) {
            out.status = "LOW";
            out.reason = "Değer kaynak rapordaki alt sınırın (≥) altında.";
            out.rule_applied = "native_value_below_greater_equal_min";
        } else {
            out.status = "NORMAL";
            out.reason = "Değer kaynak rapordaki alt sınır (≥) koşulunu sağlıyor.";
            out.rule_applied = "native_value_within_greater_equal_min";
        }
    } else if (type == "range") {
        if (out.source.reference_min && value < *out.source.reference_min) {
            out.status = "LOW";
            out.reason = "Değer kaynak rapordaki referans alt sınırının altında.";
            out.rule_applied = "native_value_below_min";
        } else if (out.source.reference_max && value > *out.source.reference_max) {
            out.status = "HIGH";
            out.reason = "Değer kaynak rapordaki referans üst sınırının üzerinde.";
            out.rule_applied = "native_value_above_max";
        } else {
            out.status = "NORMAL";
            out.reason = "Değer kaynak rapordaki mevcut referans sınırları içinde.";
            out.rule_applied = "native_value_within_reference";
        }
    } else if (type == "qualitative") {
        mark_unclassifiable(
            out,
            "NEEDS_REVIEW",
            "Referans metinsel/nitel; sayısal motor otomatik normal-düşük-yüksek kararı vermedi.",
            "native_qualitative_reference"
        );
        return out;
    } else {
        mark_unclassifiable(
            out,
            "NEEDS_REVIEW",
            "Kaynak raporda güvenilir referans sınırı bulunamadı.",
            "native_missing_reference"
        );
        return out;
    }

    out.validation_status = "VALID";
    out.classification_confidence = out.source.extraction_confidence;

    // AI/OCR ambiguity never changes the deterministic comparison itself. Instead it
    // downgrades validation and routes the original source row for human verification.
    if (out.source.ai_needs_review || out.source.extraction_confidence < 0.85) {
        out.needs_review = true;
        out.validation_status = "WARNING";
        out.classification_confidence = std::min(out.classification_confidence, 0.84);
        if (out.source.ai_needs_review) {
            out.reason += " AI çıkarımı bu satır için ayrıca kaynak doğrulaması işareti taşıyor.";
        } else {
            out.reason += " Çıkarım güveni %85 eşiğinin altında.";
        }
    }

    return out;
}

std::vector<ProcessedLabRow> process_rows(const std::vector<LabRow>& rows) {
    std::vector<ProcessedLabRow> output;
    output.reserve(rows.size());

    // Exact duplicate rows from overlapping images/PDF pages are collapsed. A
    // genuinely repeated test with a different value/reference/comparator remains separate.
    std::unordered_map<std::string, std::size_t> index_by_key;
    for (const LabRow& row : rows) {
        if (is_pseudo_parameter(row)) {
            continue;
        }

        ProcessedLabRow processed = process_row(row);
        const std::string key = make_dedupe_key(processed.source);

        auto found = index_by_key.find(key);
        if (found == index_by_key.end()) {
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
