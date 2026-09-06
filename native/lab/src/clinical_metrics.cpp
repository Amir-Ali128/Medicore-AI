#include "medicore/lab/clinical_metrics.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <optional>
#include <string>
#include <unordered_set>
#include <vector>

namespace medicore::lab {
namespace {

struct Candidate {
    const ProcessedLabRow* row{nullptr};
    double value{0.0};
};

std::string lower_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    return value;
}

std::string compact_key(const std::string& value) {
    std::string out;
    for (unsigned char c : lower_ascii(value)) {
        if (std::isalnum(c)) {
            out.push_back(static_cast<char>(c));
        }
    }
    return out;
}

bool matches_alias(const ProcessedLabRow& row, const std::unordered_set<std::string>& aliases) {
    const std::string raw = compact_key(row.source.raw_parameter_name);
    const std::string canonical = compact_key(row.source.canonical_name);
    const std::string display = compact_key(row.display_name);
    return aliases.contains(raw) || aliases.contains(canonical) || aliases.contains(display);
}

std::string unit_key(const std::string& unit) {
    std::string result;
    for (unsigned char c : lower_ascii(normalize_unit(unit))) {
        if (!std::isspace(c)) {
            result.push_back(static_cast<char>(c));
        }
    }
    return result;
}

bool confident_numeric(const ProcessedLabRow& row) {
    return row.source.normalized_value.has_value() &&
        std::isfinite(*row.source.normalized_value) &&
        !row.source.ai_needs_review &&
        row.source.extraction_confidence >= 0.85;
}

std::optional<Candidate> best_candidate(
    const std::vector<ProcessedLabRow>& rows,
    const std::unordered_set<std::string>& aliases
) {
    const ProcessedLabRow* best = nullptr;
    for (const auto& row : rows) {
        if (!confident_numeric(row) || !matches_alias(row, aliases)) {
            continue;
        }
        if (best == nullptr || row.source.extraction_confidence > best->source.extraction_confidence) {
            best = &row;
        }
    }
    if (best == nullptr) {
        return std::nullopt;
    }
    return Candidate{best, *best->source.normalized_value};
}

std::string label_for(const Candidate& candidate) {
    if (!candidate.row->display_name.empty()) {
        return candidate.row->display_name;
    }
    return candidate.row->source.raw_parameter_name;
}

bool measurement_dates_compatible(const std::vector<const Candidate*>& candidates) {
    std::string known_date;
    for (const Candidate* candidate : candidates) {
        if (candidate == nullptr) {
            return false;
        }
        const std::string date = normalize_whitespace(candidate->row->source.measured_at);
        if (date.empty()) {
            continue;
        }
        if (known_date.empty()) {
            known_date = date;
            continue;
        }
        if (date != known_date) {
            return false;
        }
    }
    return true;
}

std::optional<double> creatinine_mg_dl(const Candidate& candidate) {
    const std::string unit = unit_key(candidate.row->source.unit);
    if (unit == "mg/dl" || unit == "mgdl") {
        return candidate.value;
    }
    if (unit == "umol/l" || unit == "µmol/l" || unit == "μmol/l" || unit == "umoll") {
        return candidate.value / 88.4;
    }
    return std::nullopt;
}

std::optional<bool> female_from_sex(const std::string& sex) {
    const std::string key = compact_key(sex);
    if (key == "female" || key == "woman" || key == "f" || key == "kadin" || key == "k") {
        return true;
    }
    if (key == "male" || key == "man" || key == "m" || key == "erkek" || key == "e") {
        return false;
    }
    return std::nullopt;
}

bool hba1c_percent(const Candidate& candidate) {
    const std::string unit = unit_key(candidate.row->source.unit);
    return unit == "%" || unit == "percent" || unit.empty();
}

bool liver_enzyme_unit_ok(const Candidate& candidate) {
    const std::string unit = unit_key(candidate.row->source.unit);
    return unit.empty() || unit == "u/l" || unit == "iu/l" || unit == "ul" || unit == "iul";
}

bool platelet_unit_ok(const Candidate& candidate) {
    const std::string unit = unit_key(candidate.row->source.unit);
    if (unit.empty()) {
        return false;
    }
    return unit.find("10^9/l") != std::string::npos ||
        unit.find("109/l") != std::string::npos ||
        unit.find("x10^9/l") != std::string::npos ||
        unit.find("k/ul") != std::string::npos ||
        unit.find("k/mm3") != std::string::npos ||
        unit.find("10^3/ul") != std::string::npos ||
        unit.find("103/ul") != std::string::npos;
}

bool electrolyte_unit_ok(const Candidate& candidate) {
    const std::string unit = unit_key(candidate.row->source.unit);
    return unit == "mmol/l" || unit == "meq/l" || unit == "mmoll" || unit == "meql";
}

bool same_unit(const Candidate& a, const Candidate& b) {
    return !unit_key(a.row->source.unit).empty() && unit_key(a.row->source.unit) == unit_key(b.row->source.unit);
}

void push_metric(
    std::vector<DerivedMetric>& output,
    std::string code,
    std::string name,
    double value,
    std::string unit,
    std::string formula,
    std::vector<std::string> inputs,
    std::string note
) {
    if (!std::isfinite(value)) {
        return;
    }
    output.push_back(DerivedMetric{
        std::move(code),
        std::move(name),
        value,
        std::move(unit),
        std::move(formula),
        std::move(inputs),
        std::move(note),
    });
}

}  // namespace

std::vector<DerivedMetric> compute_derived_metrics(
    const std::vector<ProcessedLabRow>& rows,
    std::optional<int> patient_age,
    const std::string& patient_sex
) {
    std::vector<DerivedMetric> output;

    static const std::unordered_set<std::string> kCreatinine = {
        "creatinine", "creatinin", "kreatinin", "serumcreatinine", "serumkreatinin"
    };
    static const std::unordered_set<std::string> kHbA1c = {
        "hba1c", "hemoglobina1c", "glycatedhemoglobin", "glycosylatedhemoglobin"
    };
    static const std::unordered_set<std::string> kTotalCholesterol = {
        "totalcholesterol", "cholesteroltotal", "totalkolesterol", "kolesteroltotal"
    };
    static const std::unordered_set<std::string> kHdl = {
        "hdl", "hdlc", "hdlcholesterol", "hdlkolesterol"
    };
    static const std::unordered_set<std::string> kAst = {
        "ast", "sgot", "aspartateaminotransferase", "aspartataminotransferaz"
    };
    static const std::unordered_set<std::string> kAlt = {
        "alt", "sgpt", "alanineaminotransferase", "alaninaminotransferaz"
    };
    static const std::unordered_set<std::string> kPlatelets = {
        "platelet", "platelets", "plateletcount", "plt", "trombosit", "trombositler"
    };
    static const std::unordered_set<std::string> kSodium = {
        "sodium", "na", "sodyum"
    };
    static const std::unordered_set<std::string> kChloride = {
        "chloride", "cl", "klor"
    };
    static const std::unordered_set<std::string> kBicarbonate = {
        "bicarbonate", "bikarbonat", "hco3", "co2", "totalco2", "carbondioxide"
    };

    const auto creatinine = best_candidate(rows, kCreatinine);
    const auto female = female_from_sex(patient_sex);
    if (creatinine && patient_age && *patient_age >= 18 && *patient_age <= 120 && female) {
        const auto scr = creatinine_mg_dl(*creatinine);
        if (scr && *scr > 0.0) {
            const double kappa = *female ? 0.7 : 0.9;
            const double alpha = *female ? -0.241 : -0.302;
            const double ratio = *scr / kappa;
            double egfr = 142.0 * std::pow(std::min(ratio, 1.0), alpha) *
                std::pow(std::max(ratio, 1.0), -1.200) *
                std::pow(0.9938, static_cast<double>(*patient_age));
            if (*female) {
                egfr *= 1.012;
            }
            push_metric(
                output,
                "egfr_ckd_epi_2021",
                "eGFR (CKD-EPI 2021)",
                egfr,
                "mL/min/1.73m²",
                "142 × min(SCr/κ,1)^α × max(SCr/κ,1)^-1.200 × 0.9938^Age × 1.012 if female",
                {label_for(*creatinine), "age", "sex"},
                "2021 CKD-EPI creatinine estimate. A single eGFR value does not establish chronic kidney disease."
            );
        }
    }

    const auto hba1c = best_candidate(rows, kHbA1c);
    if (hba1c && hba1c_percent(*hba1c) && hba1c->value >= 0.0 && hba1c->value <= 30.0) {
        push_metric(
            output,
            "estimated_average_glucose",
            "Estimated Average Glucose",
            28.7 * hba1c->value - 46.7,
            "mg/dL",
            "28.7 × HbA1c - 46.7",
            {label_for(*hba1c)},
            "NGSP/ADAG estimated average glucose relationship; this is a calculated estimate, not a measured glucose result."
        );
    }

    const auto total_cholesterol = best_candidate(rows, kTotalCholesterol);
    const auto hdl = best_candidate(rows, kHdl);
    if (total_cholesterol && hdl && same_unit(*total_cholesterol, *hdl) &&
        measurement_dates_compatible({&*total_cholesterol, &*hdl}) &&
        total_cholesterol->value >= hdl->value) {
        push_metric(
            output,
            "non_hdl_cholesterol",
            "Non-HDL Cholesterol",
            total_cholesterol->value - hdl->value,
            total_cholesterol->row->source.unit,
            "Total cholesterol - HDL cholesterol",
            {label_for(*total_cholesterol), label_for(*hdl)},
            "Calculated lipid value using source results with matching units and compatible measurement dates."
        );
    }

    const auto ast = best_candidate(rows, kAst);
    const auto alt = best_candidate(rows, kAlt);
    const auto platelets = best_candidate(rows, kPlatelets);
    if (patient_age && *patient_age >= 18 && *patient_age <= 120 && ast && alt && platelets &&
        measurement_dates_compatible({&*ast, &*alt, &*platelets}) &&
        liver_enzyme_unit_ok(*ast) && liver_enzyme_unit_ok(*alt) && platelet_unit_ok(*platelets) &&
        ast->value >= 0.0 && alt->value > 0.0 && platelets->value > 0.0) {
        const double fib4 = static_cast<double>(*patient_age) * ast->value /
            (platelets->value * std::sqrt(alt->value));
        const std::string age_note = *patient_age > 65
            ? " Age over 65 can increase FIB-4 and reduce specificity; interpret in clinical context."
            : "";
        push_metric(
            output,
            "fib4",
            "FIB-4",
            fib4,
            "index",
            "Age × AST / (platelets × sqrt(ALT))",
            {"age", label_for(*ast), label_for(*alt), label_for(*platelets)},
            "Non-invasive fibrosis risk index; it is not a diagnosis of liver fibrosis." + age_note
        );
    }

    const auto sodium = best_candidate(rows, kSodium);
    const auto chloride = best_candidate(rows, kChloride);
    const auto bicarbonate = best_candidate(rows, kBicarbonate);
    if (sodium && chloride && bicarbonate &&
        measurement_dates_compatible({&*sodium, &*chloride, &*bicarbonate}) &&
        electrolyte_unit_ok(*sodium) && electrolyte_unit_ok(*chloride) &&
        electrolyte_unit_ok(*bicarbonate)) {
        push_metric(
            output,
            "anion_gap_without_potassium",
            "Anion Gap",
            sodium->value - chloride->value - bicarbonate->value,
            "mmol/L",
            "Na - Cl - HCO3",
            {label_for(*sodium), label_for(*chloride), label_for(*bicarbonate)},
            "Calculated without potassium and only when source electrolyte units and measurement dates are compatible."
        );
    }

    return output;
}

}  // namespace medicore::lab
