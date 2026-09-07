#include "medicore/lab/deterministic_core.hpp"

#include <algorithm>
#include <cmath>
#include <cctype>
#include <iomanip>
#include <sstream>
#include <tuple>

namespace medicore::lab {
namespace {

std::string replace_all(std::string value, const std::string& from, const std::string& to) {
    std::size_t pos = 0;
    while ((pos = value.find(from, pos)) != std::string::npos) {
        value.replace(pos, from.size(), to);
        pos += to.size();
    }
    return value;
}

std::string fold_latin_utf8(std::string value) {
    const std::pair<const char*, const char*> replacements[] = {
        {"ı", "i"}, {"İ", "i"}, {"ş", "s"}, {"Ş", "s"},
        {"ğ", "g"}, {"Ğ", "g"}, {"ç", "c"}, {"Ç", "c"},
        {"ö", "o"}, {"Ö", "o"}, {"ü", "u"}, {"Ü", "u"},
        {"á", "a"}, {"à", "a"}, {"â", "a"}, {"ä", "a"}, {"ã", "a"}, {"å", "a"},
        {"Á", "a"}, {"À", "a"}, {"Â", "a"}, {"Ä", "a"}, {"Ã", "a"}, {"Å", "a"},
        {"é", "e"}, {"è", "e"}, {"ê", "e"}, {"ë", "e"},
        {"É", "e"}, {"È", "e"}, {"Ê", "e"}, {"Ë", "e"},
        {"í", "i"}, {"ì", "i"}, {"î", "i"}, {"ï", "i"},
        {"Í", "i"}, {"Ì", "i"}, {"Î", "i"}, {"Ï", "i"},
        {"ó", "o"}, {"ò", "o"}, {"ô", "o"}, {"õ", "o"},
        {"Ó", "o"}, {"Ò", "o"}, {"Ô", "o"}, {"Õ", "o"},
        {"ú", "u"}, {"ù", "u"}, {"û", "u"},
        {"Ú", "u"}, {"Ù", "u"}, {"Û", "u"},
        {"ñ", "n"}, {"Ñ", "n"},
    };
    for (const auto& [from, to] : replacements) {
        value = replace_all(std::move(value), from, to);
    }
    return value;
}

std::size_t gestalt_match_sum(
    const std::string& a,
    std::size_t a0,
    std::size_t a1,
    const std::string& b,
    std::size_t b0,
    std::size_t b1
) {
    if (a0 >= a1 || b0 >= b1) {
        return 0;
    }

    const std::size_t n = a1 - a0;
    const std::size_t m = b1 - b0;
    std::vector<std::size_t> prev(m + 1, 0);
    std::vector<std::size_t> curr(m + 1, 0);

    std::size_t best_len = 0;
    std::size_t best_a_end = a0;
    std::size_t best_b_end = b0;

    for (std::size_t i = 1; i <= n; ++i) {
        std::fill(curr.begin(), curr.end(), 0);
        for (std::size_t j = 1; j <= m; ++j) {
            if (a[a0 + i - 1] == b[b0 + j - 1]) {
                curr[j] = prev[j - 1] + 1;
                if (curr[j] > best_len) {
                    best_len = curr[j];
                    best_a_end = a0 + i;
                    best_b_end = b0 + j;
                }
            }
        }
        prev.swap(curr);
    }

    if (best_len == 0) {
        return 0;
    }

    const std::size_t best_a_start = best_a_end - best_len;
    const std::size_t best_b_start = best_b_end - best_len;

    return best_len +
        gestalt_match_sum(a, a0, best_a_start, b, b0, best_b_start) +
        gestalt_match_sum(a, best_a_end, a1, b, best_b_end, b1);
}

bool finite_optional(const std::optional<double>& value) {
    return !value.has_value() || std::isfinite(*value);
}

std::string percent_suffix(const std::optional<double>& percentage) {
    if (!percentage) {
        return {};
    }
    std::ostringstream out;
    out << " (" << std::showpos << std::fixed << std::setprecision(2) << *percentage << "%)";
    return out.str();
}

std::string number_with_sign(double value) {
    std::ostringstream out;
    out << std::showpos << value;
    return out.str();
}

std::string upper_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::toupper(c));
    });
    return value;
}

bool compatible(
    const ReferenceCandidate& candidate,
    const std::string& patient_sex,
    const std::optional<int>& patient_age,
    const std::optional<bool>& pregnancy_status
) {
    const std::string sex = upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex);
    const std::string patient = upper_ascii(patient_sex);
    if (sex != "ANY") {
        if (patient.empty() || sex != patient) {
            return false;
        }
    }

    if (candidate.pregnancy_status.has_value()) {
        if (!pregnancy_status.has_value() || *candidate.pregnancy_status != *pregnancy_status) {
            return false;
        }
    }

    if (candidate.age_min || candidate.age_max) {
        if (!patient_age) {
            return false;
        }
        if (candidate.age_min && *patient_age < *candidate.age_min) {
            return false;
        }
        if (candidate.age_max && *patient_age > *candidate.age_max) {
            return false;
        }
    }
    return true;
}

bool requires_no_inputs(const ReferenceCandidate& candidate) {
    return upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex) == "ANY" &&
        !candidate.age_min && !candidate.age_max && !candidate.pregnancy_status.has_value();
}

double specificity(const ReferenceCandidate& candidate) {
    double score = 0.0;
    if (upper_ascii(candidate.sex.empty() ? "ANY" : candidate.sex) != "ANY") {
        score += 2.0;
    }
    if (candidate.pregnancy_status.has_value()) {
        score += 2.0;
    }
    if (candidate.age_min) {
        score += 0.5;
    }
    if (candidate.age_max) {
        score += 0.5;
    }
    return score;
}

bool same_effective_range(const ReferenceCandidate& left, const ReferenceCandidate& right) {
    return left.reference_min == right.reference_min &&
        left.reference_max == right.reference_max &&
        normalize_alias(left.unit) == normalize_alias(right.unit);
}

}  // namespace

std::string normalize_alias(const std::string& value) {
    std::string folded = fold_latin_utf8(value);
    std::string out;
    out.reserve(folded.size());
    bool pending_space = false;

    for (unsigned char ch : folded) {
        if (ch < 128) {
            if (std::isalnum(ch)) {
                if (pending_space && !out.empty()) {
                    out.push_back(' ');
                }
                out.push_back(static_cast<char>(std::tolower(ch)));
                pending_space = false;
            } else {
                pending_space = !out.empty();
            }
        } else {
            // Unknown non-ASCII code points are treated as separators. All Turkish
            // and common Latin diacritics are folded above before this branch.
            pending_space = !out.empty();
        }
    }

    while (!out.empty() && out.back() == ' ') {
        out.pop_back();
    }
    return out;
}

double alias_similarity_ratio(const std::string& left, const std::string& right) {
    const std::string a = normalize_alias(left);
    const std::string b = normalize_alias(right);
    if (a.empty() && b.empty()) {
        return 1.0;
    }
    if (a.empty() || b.empty()) {
        return 0.0;
    }
    const std::size_t matches = gestalt_match_sum(a, 0, a.size(), b, 0, b.size());
    return (2.0 * static_cast<double>(matches)) /
        static_cast<double>(a.size() + b.size());
}

RuleEvaluation evaluate_rule(
    bool parameter_known,
    bool alias_needs_review,
    bool reference_needs_review,
    const std::optional<double>& normalized_value,
    const std::optional<double>& reference_min,
    const std::optional<double>& reference_max
) {
    RuleEvaluation out;
    auto review = [&](const std::string& rule, const std::string& reason) {
        out.status = "NEEDS_REVIEW";
        out.rule_applied = rule;
        out.reason = reason;
        out.confidence = 0.0;
        out.needs_review = true;
        return out;
    };

    if (!parameter_known) {
        out.status = "UNKNOWN";
        out.rule_applied = "unknown_parameter";
        out.reason = "Parameter could not be identified.";
        out.confidence = 0.0;
        out.needs_review = true;
        return out;
    }
    if (alias_needs_review) {
        return review("alias_needs_review", "Alias resolution is uncertain; human review required.");
    }
    if (reference_needs_review) {
        return review("reference_needs_review", "Reference range is uncertain; human review required.");
    }
    if (!finite_optional(normalized_value) || !finite_optional(reference_min) || !finite_optional(reference_max)) {
        return review("non_finite_numeric", "One or more numeric fields are not finite.");
    }
    if (!normalized_value) {
        return review("missing_value", "No structured numeric value available.");
    }
    if (!reference_min || !reference_max) {
        return review("missing_reference_bounds", "Reference minimum and/or maximum is missing.");
    }
    if (*reference_min > *reference_max) {
        return review("invalid_reference_range", "Reference minimum is greater than reference maximum.");
    }

    out.confidence = 1.0;
    out.needs_review = false;
    if (*normalized_value < *reference_min) {
        out.status = "LOW";
        out.rule_applied = "value_below_min";
        out.reason = "Value is below reference minimum.";
    } else if (*normalized_value > *reference_max) {
        out.status = "HIGH";
        out.rule_applied = "value_above_max";
        out.reason = "Value is above reference maximum.";
    } else {
        out.status = "NORMAL";
        out.rule_applied = "value_within_range";
        out.reason = "Value is within the inclusive reference range.";
    }
    return out;
}

TrendEvaluation compare_trend(
    const std::optional<double>& current_value,
    const std::optional<double>& previous_value,
    const std::optional<int>& time_difference_days,
    double stable_relative_threshold
) {
    TrendEvaluation out;
    out.current_value = current_value;
    out.previous_value = previous_value;
    out.time_difference_days = time_difference_days;

    if (!previous_value) {
        out.reason = "No previous result available for comparison.";
        out.confidence = 0.0;
        return out;
    }
    if (!current_value || !finite_optional(current_value) || !finite_optional(previous_value)) {
        out.reason = "Current and/or previous value is missing or non-numeric.";
        out.needs_review = true;
        out.confidence = 0.0;
        return out;
    }

    const double diff = *current_value - *previous_value;
    out.absolute_difference = diff;
    if (*previous_value != 0.0) {
        out.percentage_difference = (diff / *previous_value) * 100.0;
    }

    if (diff == 0.0 ||
        (out.percentage_difference &&
         std::abs(*out.percentage_difference) <= stable_relative_threshold * 100.0)) {
        out.status = "STABLE";
    } else {
        out.status = diff > 0.0 ? "UP" : "DOWN";
    }

    out.confidence = time_difference_days ? 1.0 : 0.8;
    const std::string pct = percent_suffix(out.percentage_difference);
    if (out.status == "STABLE") {
        out.reason = "Change " + number_with_sign(diff) + pct + " is within the stable band.";
    } else if (out.status == "UP") {
        out.reason = "Value increased by " + number_with_sign(diff) + pct + ".";
    } else {
        out.reason = "Value decreased by " + number_with_sign(diff) + pct + ".";
    }
    return out;
}

ReferenceSelection select_reference_candidate(
    const std::vector<ReferenceCandidate>& candidates,
    const std::string& patient_sex,
    const std::optional<int>& patient_age,
    const std::optional<bool>& pregnancy_status
) {
    ReferenceSelection out;

    std::vector<std::size_t> compatible_indices;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (compatible(candidates[i], patient_sex, patient_age, pregnancy_status)) {
            compatible_indices.push_back(i);
        }
    }
    if (!compatible_indices.empty()) {
        std::stable_sort(compatible_indices.begin(), compatible_indices.end(), [&](std::size_t left, std::size_t right) {
            return specificity(candidates[left]) > specificity(candidates[right]);
        });
        const double best_score = specificity(candidates[compatible_indices.front()]);
        std::size_t tied = 0;
        for (const std::size_t index : compatible_indices) {
            if (specificity(candidates[index]) == best_score) {
                ++tied;
            }
        }
        out.index = compatible_indices.front();
        out.strategy = "database_demographic";
        out.needs_review = tied > 1;
        out.confidence = out.needs_review ? 0.70 : 0.90;
        out.reason = "Matched a demographic reference range fully compatible with the provided patient inputs.";
        if (out.needs_review) {
            out.reason += " Multiple equally-specific ranges matched; review needed.";
        }
        return out;
    }

    std::vector<std::size_t> generic;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (requires_no_inputs(candidates[i])) {
            generic.push_back(i);
        }
    }
    if (!generic.empty()) {
        out.index = generic.front();
        out.strategy = "database_default";
        out.needs_review = generic.size() > 1;
        out.confidence = 0.60;
        out.reason = "Using a general, input-independent reference range.";
        if (out.needs_review) {
            out.reason += " Multiple general ranges exist; review needed.";
        }
        return out;
    }

    std::vector<std::size_t> usable;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (candidates[i].reference_min && candidates[i].reference_max && !candidates[i].unit.empty()) {
            usable.push_back(i);
        }
    }
    if (!usable.empty()) {
        const auto& first = candidates[usable.front()];
        bool identical = true;
        for (const std::size_t index : usable) {
            if (!same_effective_range(first, candidates[index])) {
                identical = false;
                break;
            }
        }
        if (identical) {
            out.index = usable.front();
            out.strategy = "database_default";
            out.needs_review = false;
            out.confidence = 0.85;
            out.reason = "Using a stored reference range because all demographic ranges for this parameter have identical bounds and unit.";
            return out;
        }
    }

    out.index = std::nullopt;
    out.strategy = "needs_review";
    out.confidence = 0.0;
    out.needs_review = true;
    out.reason = "No reference range is safely resolvable from the provided patient inputs.";
    return out;
}

}  // namespace medicore::lab
