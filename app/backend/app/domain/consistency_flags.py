"""Deterministic provenance warnings; no clinical interpretation or value changes."""
import re
from collections.abc import Mapping
from app.domain.consistency_config import DATE_FIELDS, HIGH_SEVERITY, INFO_CODES, MESSAGES_TR, CONSISTENCY_HEADING, NO_INCONSISTENCY


def codes(value):
    return [value] if isinstance(value, str) else list(value) if isinstance(value, (list, tuple)) else []


def make_flag(code, parameter, *, date=None, page=None, row=None):
    code = str(code)
    def position(value):
        try:
            return int(value) if not isinstance(value, bool) and int(value) > 0 else None
        except (TypeError, ValueError, OverflowError):
            return None
    return {"code": str(code), "severity": "high" if code in HIGH_SEVERITY else "info" if code in INFO_CODES else "warning",
            "parameter_or_report": str(parameter), "date": str(date) if date is not None else None,
            "source_page": position(page), "source_row": position(row),
            "message_tr": MESSAGES_TR.get(str(code), f"Kaynak veride ek denetim uyarısı: {code}")}


def collect_consistency_flags(payload):
    flags, documents = [], {}
    for lab in payload.labs:
        metadata = lab.source_metadata if isinstance(lab.source_metadata, Mapping) else {}
        day = next((getattr(lab, field, None) or metadata.get(field) for field in DATE_FIELDS if getattr(lab, field, None) or metadata.get(field)), None)
        locations = metadata.get("source_locations") or [{"page": metadata.get("source_page"), "row": metadata.get("source_row")}]
        for code in codes(metadata.get("ingestion_reasons")):
            for location in locations:
                if isinstance(location, Mapping):
                    flags.append(make_flag(code, lab.test_name, date=day, page=location.get("page"), row=location.get("row")))
        for warning in codes(metadata.get("document_warnings")):
            match = re.fullmatch(r"page_(\d+):(.+)", str(warning))
            page, code = (int(match[1]), match[2]) if match else (metadata.get("source_page"), str(warning))
            key = (metadata.get("source_file_name") or "Belge", page, code)
            documents[key] = make_flag(code, key[0], page=page)
    flags.extend(documents.values())
    for index, report in enumerate(payload.reports, 1):
        metadata = report.metadata if isinstance(report.metadata, Mapping) else {}
        for code in codes(metadata.get("ingestion_reasons")):
            flags.append(make_flag(code, metadata.get("source_file_name") or f"{report.report_type} #{index}", date=report.report_date,
                                   page=metadata.get("source_page"), row=metadata.get("source_row")))
    seen, unique = set(), []
    for flag in flags:
        key = tuple(str(value) for value in flag.values())
        if key not in seen:
            unique.append(flag); seen.add(key)
    return unique


def render_consistency_section(flags):
    lines = [CONSISTENCY_HEADING]
    for flag in flags:
        parameter = " ".join(flag['parameter_or_report'].split())
        location = f"Sayfa {flag['source_page'] or 'belirtilmedi'} · Satır {flag['source_row'] or 'belirtilmedi'}"
        lines.append(f"- {parameter} · {flag['date'] or 'Tarih belirtilmedi'} · {location}: {flag['message_tr']} [{flag['code']}]")
    if not flags:
        lines.append(NO_INCONSISTENCY)
    return "\n".join(lines) + "\n\n"
