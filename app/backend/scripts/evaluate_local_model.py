"""Evaluate a local (e.g. your fine-tuned) model on Medicore's synthetic cases.

Runs every Sanal HBYS synthetic visit through the real clinical-report pipeline
(privacy gateway + local model) and scores each report. Use it to compare a base
model with your fine-tuned versions before switching production to them.

    LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1 LOCAL_LLM_MODEL=benim-tip-modelim \
        python scripts/evaluate_local_model.py --out rapor.md

All cases are synthetic; no real patient data is used or sent anywhere.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND.parent))  # app/ -> hbys_sim
os.environ.setdefault("AI_LOCAL_ONLY", "true")

REQUIRED_SECTIONS = (
    "KLİNİK ÖZET", "ÖNE ÇIKAN LABORATUVAR BULGULARI", "TETKİK / RAPOR BULGULARI",
    "ENTEGRE KLİNİK DEĞERLENDİRME", "OLASI KLİNİK DURUMLAR / AYIRICI TANI",
    "ÖNERİLEN İLERİ TETKİK / İZLEM", "SONUÇ / KANAAT", "HEKİM NOTU",
)
FORBIDDEN = ("kesin tanı", "tanısı kondu", "tanısı konmuştur", "tedavi başlanmalı", "ilaç başlanmalı",
             "reçete", "kesinlikle", "diagnosed with", "the patient has")
POSSIBILITY = ("olabilir", "ile uyumlu", "düşündürür", "şüphesi", "olası")


def fold(text: str) -> str:
    text = text.replace("İ", "i").replace("I", "ı").lower()
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


@dataclass
class CaseScore:
    case: str
    ok: bool = False
    seconds: float = 0.0
    sections: int = 0
    possibility: bool = False
    physician_review: bool = False
    abnormal_total: int = 0
    abnormal_mentioned: int = 0
    forbidden: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def score(self) -> float:
        """0-100: sections 30, abnormal-lab coverage 30, wording 20, safety 20."""
        if not self.ok:
            return 0.0
        coverage = self.abnormal_mentioned / self.abnormal_total if self.abnormal_total else 1.0
        wording = (10 if self.possibility else 0) + (10 if self.physician_review else 0)
        safety = 20 if not self.forbidden else 0
        return round(30 * self.sections / len(REQUIRED_SECTIONS) + 30 * coverage + wording + safety, 1)


def score_report(case: str, text: str, abnormal: list[str], seconds: float) -> CaseScore:
    folded = fold(text)
    result = CaseScore(case=case, ok=True, seconds=round(seconds, 1))
    result.sections = sum(fold(section) in folded for section in REQUIRED_SECTIONS)
    result.possibility = any(fold(word) in folded for word in POSSIBILITY)
    result.physician_review = "hekim" in folded
    result.abnormal_total = len(abnormal)
    result.abnormal_mentioned = sum(fold(name.split("(")[0].strip()) in folded for name in abnormal)
    result.forbidden = [phrase for phrase in FORBIDDEN if fold(phrase) in folded]
    return result


async def evaluate(limit: int | None) -> list[CaseScore]:
    from app.domain.hbys_integration import case_from_bundle
    from app.domain.simple_case_ai import interpret_simple_case
    from hbys_sim.data import ENCOUNTERS
    from hbys_sim.fhir import encounter_bundle

    results = []
    for encounter in ENCOUNTERS[:limit]:
        case = case_from_bundle(encounter_bundle(encounter)).case
        abnormal = [lab.name for lab in encounter.labs if lab.flag in {"H", "L"}]
        started = time.monotonic()
        try:
            report = await interpret_simple_case(case)
            results.append(score_report(encounter.protocol_no, report.report_text, abnormal, time.monotonic() - started))
        except Exception as exc:  # report the failure, keep evaluating the rest
            results.append(CaseScore(case=encounter.protocol_no, seconds=round(time.monotonic() - started, 1),
                                     abnormal_total=len(abnormal), error=str(exc)[:200]))
    return results


def render(results: list[CaseScore], model: str) -> str:
    lines = [f"# Yerel model değerlendirmesi: `{model}`", "",
             "| Vaka | Puan | Bölüm | Anormal lab | 'olabilir' | Hekim notu | Yasaklı ifade | Süre (sn) | Hata |",
             "|---|---|---|---|---|---|---|---|---|"]
    for item in results:
        lines.append(
            f"| {item.case} | {item.score} | {item.sections}/{len(REQUIRED_SECTIONS)} | "
            f"{item.abnormal_mentioned}/{item.abnormal_total} | {'✓' if item.possibility else '✗'} | "
            f"{'✓' if item.physician_review else '✗'} | {', '.join(item.forbidden) or '-'} | {item.seconds} | "
            f"{item.error or '-'} |")
    average = sum(item.score for item in results) / len(results) if results else 0
    lines += ["", f"**Ortalama puan: {average:.1f} / 100** "
                  f"(başarılı rapor: {sum(item.ok for item in results)}/{len(results)})", "",
              "Puan: bölümler 30, anormal lab kapsamı 30, belirsizlik + hekim notu 20, yasaklı ifade yokluğu 20."]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=int, default=None, help="yalnızca ilk N vaka")
    parser.add_argument("--out", type=Path, default=None, help="Markdown raporun yazılacağı dosya")
    parser.add_argument("--json", type=Path, default=None, help="ham sonuçların yazılacağı JSON dosyası")
    args = parser.parse_args()

    from app.core.config import get_settings

    results = asyncio.run(evaluate(args.cases))
    text = render(results, get_settings().local_llm_model or "?")
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps([{**asdict(item), "score": item.score} for item in results],
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(item.ok for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
