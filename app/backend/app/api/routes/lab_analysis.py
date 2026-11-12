"""Lab report analysis routes.




MVP PDF parser for text-based lab reports.




Fixes in this version:
- Reads full lab rows using value + unit + reference parsing.
- Ignores header garbage such as "Kreatinin, idrar7890..."
- Avoids using digits inside units such as K/mm3, M/mm3, mL/dk/1.73m2
  as reference ranges.
- Uses separate marker names for absolute differential cells:
  Nötrofil Mutlak, Lenfosit Mutlak, Monosit Mutlak, Eozinofil Mutlak, Bazofil Mutlak.
- Converts one-sided decision limits into safe demo ranges:
  GFR/HDL: lower-bound style, Total Kolesterol/Trigliserit/LDL: upper-bound style.
"""




from __future__ import annotations

from app.domain.privacy_gateway import PrivacyViolation




import io
import re
import uuid
from datetime import date, datetime
from typing import Any
from uuid import UUID




from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import text as sql_text




from app.api.dependencies import AnalysisPipelineDep
from app.domain.enums import Sex, UserRole
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory
from app.schemas.lab_analysis import AnalysisPipelineResult, MockLabReportInput, PatientMetadataOutput








router = APIRouter(prefix="/lab-analysis", tags=["lab-analysis"])




_PATIENT_NOT_FOUND = "Patient not found."
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024




DEMO_PATIENT_ID = UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
DEMO_UPLOADED_BY_USER_ID = UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")






async def _ensure_render_demo_clinical_parameters(session: Any) -> None:
    """Upsert demo clinical parameter rows missing from fresh Render databases.


    The PDF parser sends these raw names as parameter codes so AliasEngine can
    resolve them deterministically without fuzzy/uncertain matching.
    """
    parameters = [
        ("GFR", "GFR", "mL/dk/1.73m2"),
        ("TRIGLISERIT", "Trigliserit", "mg/dL"),
        ("FT3", "FT3", "pmol/L"),
        ("FT4", "FT4", "pmol/L"),
        ("VITAMIN_B1", "Vitamin B1", "ug/L"),
        ("SEDIMENTASYON", "Sedimentasyon", "mm/S"),
        ("NOTROFIL_MUTLAK", "Nötrofil Mutlak", "K/mm3"),
        ("LENFOSIT_MUTLAK", "Lenfosit Mutlak", "K/mm3"),
        ("MONOSIT_MUTLAK", "Monosit Mutlak", "K/mm3"),
        ("EOZINOFIL_MUTLAK", "Eozinofil Mutlak", "K/mm3"),
        ("BAZOFIL_MUTLAK", "Bazofil Mutlak", "K/mm3"),
        ("BUN", "BUN", "mg/dL"),
        ("KREATININ", "Kreatinin", "mg/dL"),
        ("BUN_KREATININ_ORANI", "BUN / Kreatinin", ""),
        ("NON_HDL", "Non-HDL", "mg/dL"),
        ("IG_MUTLAK", "IG Mutlak", "K/mm3"),
        ("IG_YUZDE", "IG %", "%"),
    ]


    for parameter_code, canonical_name, default_unit in parameters:
        existing = await session.execute(
            sql_text(
                """
                SELECT id
                FROM clinical_parameters
                WHERE parameter_code = :parameter_code
                   OR canonical_name = :canonical_name
                LIMIT 1
                """
            ),
            {
                "parameter_code": parameter_code,
                "canonical_name": canonical_name,
            },
        )


        existing_id = existing.scalar_one_or_none()


        if existing_id is None:
            await session.execute(
                sql_text(
                    """
                    INSERT INTO clinical_parameters (
                        id,
                        parameter_code,
                        canonical_name,
                        default_unit,
                        active_phase1,
                        analysis_level,
                        metadata_json,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :id,
                        :parameter_code,
                        :canonical_name,
                        :default_unit,
                        true,
                        (
                            SELECT enumlabel::analysis_level
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'analysis_level'
                              AND enumlabel <> 'L0'
                            ORDER BY enumsortorder
                            LIMIT 1
                        ),
                        '{"source":"render_upload_bootstrap"}'::jsonb,
                        NOW(),
                        NOW()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"medicore-demo:{parameter_code}")),
                    "parameter_code": parameter_code,
                    "canonical_name": canonical_name,
                    "default_unit": default_unit,
                },
            )
        else:
            await session.execute(
                sql_text(
                    """
                    UPDATE clinical_parameters
                    SET
                        parameter_code = :parameter_code,
                        canonical_name = :canonical_name,
                        default_unit = COALESCE(default_unit, :default_unit),
                        active_phase1 = true,
                        analysis_level = (
                            SELECT enumlabel::analysis_level
                            FROM pg_enum
                            JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                            WHERE pg_type.typname = 'analysis_level'
                              AND enumlabel <> 'L0'
                            ORDER BY enumsortorder
                            LIMIT 1
                        ),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing_id,
                    "parameter_code": parameter_code,
                    "canonical_name": canonical_name,
                    "default_unit": default_unit,
                },
            )




async def _ensure_demo_patient_and_user() -> None:
    """Create demo patient/user in fresh Render databases if missing."""
    async with AsyncSessionFactory() as session:
        await _ensure_render_demo_clinical_parameters(session)
        patient = await session.get(Patient, DEMO_PATIENT_ID)


        if patient is None:
            patient = Patient(
                id=DEMO_PATIENT_ID,
                external_ref="demo-render-patient",
                sex=Sex.MALE,
                date_of_birth=date(2004, 1, 1),
                is_pregnant=False,
                metadata_json={"source": "render_demo_auto_seed"},
            )
            session.add(patient)


        user = await session.get(User, DEMO_UPLOADED_BY_USER_ID)


        if user is None:
            user = User(
                id=DEMO_UPLOADED_BY_USER_ID,
                email="demo-upload@medicore.ai",
                hashed_password="not-used-demo-upload-user",
                full_name="Demo Upload User",
                role=UserRole.DOCTOR,
                is_active=True,
                is_superuser=False,
            )
            session.add(user)


        # Render bootstrap guard:
        # Fresh Render DBs can contain imported clinical parameters that are still
        # inactive/L0. The Phase 1 analysis pipeline rejects those before it can
        # classify values, causing every PDF result to become NEEDS_REVIEW.
        await session.execute(
            sql_text(
                """
                UPDATE clinical_parameters
                SET
                    active_phase1 = true,
                    analysis_level = (
                        SELECT enumlabel::analysis_level
                        FROM pg_enum
                        JOIN pg_type ON pg_enum.enumtypid = pg_type.oid
                        WHERE pg_type.typname = 'analysis_level'
                          AND enumlabel <> 'L0'
                        ORDER BY enumsortorder
                        LIMIT 1
                    ),
                    updated_at = NOW()
                WHERE active_phase1 IS NOT TRUE
                   OR analysis_level = 'L0'::analysis_level
                """
            )
        )


        await session.commit()












LAB_PARAMETER_ALIASES: dict[str, dict[str, Any]] = {
    # Kidney / glucose
    "BUN": {
        "aliases": ["KAN URE NITROJENI (BUN)", "KAN URE NITROJENI", "BUN"],
        "default_unit": "mg/dL",
    },
    "Kreatinin": {
        "aliases": ["KREATININ", "CREATININE", "CREA"],
        "default_unit": "mg/dL",
    },
    "GFR": {
        "aliases": [
            "GLOMERULER FILTRASYON HIZI (HGFR)",
            "GLOMERULER FILTRASYON HIZI",
            "HGFR",
            "EGFR",
            "GFR",
        ],
        "default_unit": "mL/dk/1.73m2",
    },
    "BUN / Kreatinin": {
        "aliases": ["BUN / KREATININ", "BUN/KREATININ", "BUN CREATININE RATIO"],
        "default_unit": "",
    },
    "Glukoz": {
        "aliases": ["GLUKOZ (ACLIK KAN SEKERI)", "ACLIK KAN SEKERI", "GLUKOZ", "GLUCOSE"],
        "default_unit": "mg/dL",
    },




    # Lipids / decision thresholds
    "Total Kolesterol": {
        "aliases": ["TOTAL KOLESTEROL", "TOTAL CHOLESTEROL", "CHOLESTEROL"],
        "default_unit": "mg/dL",
    },
    "HDL": {
        "aliases": ["HDL-KOLESTEROL", "HDL KOLESTEROL", "HDL CHOLESTEROL", "HDL"],
        "default_unit": "mg/dL",
    },
    "TRIGLISERIT": {
        "aliases": ["TRIGLISERIT", "TRIGLYCERIDE", "TRIGLYCERIDES", "TRIG"],
        "default_unit": "mg/dL",
    },
    "LDL": {
        "aliases": ["LDL-KOLESTEROL", "LDL KOLESTEROL", "LDL CHOLESTEROL", "LDL"],
        "default_unit": "mg/dL",
    },
    "Non-HDL": {
        "aliases": [
            "NON-HDL",
            "NON HDL",
            "NON-HDL KOLESTEROL",
            "NON HDL KOLESTEROL",
            "NON-HDL-KOLESTEROL",
            "NON HDL CHOLESTEROL",
            "NON-HDL CHOLESTEROL",
        ],
        "default_unit": "mg/dL",
    },




    # Liver / bilirubin
    "ALP": {
        "aliases": ["ALP(ALKALEN FOSFATAZ)", "ALP (ALKALEN FOSFATAZ)", "ALKALEN FOSFATAZ", "ALP"],
        "default_unit": "IU/L",
    },
    "AST": {
        "aliases": ["AST (ASPARTAT AMINOTRANSFERAZ)", "ASPARTAT AMINOTRANSFERAZ", "AST"],
        "default_unit": "IU/L",
    },
    "ALT": {
        "aliases": ["ALT (ALANIN AMINOTRANSFERAZ)", "ALANIN AMINOTRANSFERAZ", "ALT"],
        "default_unit": "IU/L",
    },
    "GGT": {
        "aliases": ["GAMA-GT (GLUTAMIL TRANSFERAZ)", "GLUTAMIL TRANSFERAZ", "GAMA-GT", "GAMA GT", "GGT"],
        "default_unit": "IU/L",
    },
    "Total Bilirubin": {
        "aliases": ["TOTAL BILIRUBIN", "BILIRUBIN TOTAL"],
        "default_unit": "mg/dL",
    },
    "Direkt Bilirubin": {
        "aliases": ["DIREKT BILIRUBIN", "DIRECT BILIRUBIN", "BILIRUBIN DIRECT"],
        "default_unit": "mg/dL",
    },




    # Thyroid / vitamins / inflammation
    "FT3": {
        "aliases": ["FT3 (SERBEST TRIIODOTIRONIN)", "SERBEST TRIIODOTIRONIN", "FT3"],
        "default_unit": "pmol/L",
    },
    "FT4": {
        "aliases": ["FT4 (SERBEST TIROKSIN)", "SERBEST TIROKSIN", "FT4"],
        "default_unit": "pmol/L",
    },
    "TSH": {
        "aliases": ["S-TSH (TIROID STIMULAN HORMON)", "TIROID STIMULAN HORMON", "S-TSH", "TSH"],
        "default_unit": "uIU/mL",
    },
    "Vitamin B12": {
        "aliases": ["VITAMIN B12", "B12"],
        "default_unit": "pg/mL",
    },
    "Vitamin D": {
        "aliases": ["25-OH VITAMIN D, TOTAL, LC MS/MS", "25-OH VITAMIN D", "25 OH VITAMIN D", "VITAMIN D"],
        "default_unit": "ng/mL",
    },
    "VITAMIN_B1": {
        "aliases": ["VITAMIN B1, TAM KAN", "VITAMIN B1", "B1"],
        "default_unit": "ug/L",
    },
    "SEDIMENTASYON": {
        "aliases": ["SEDIMANTASYON HIZI (1 SAAT)", "SEDIMANTASYON HIZI", "ESR"],
        "default_unit": "mm/S",
    },
    "CRP": {
        "aliases": ["CRP"],
        "default_unit": "mg/L",
    },
    "FOLIK_ASIT": {
        "aliases": ["FOLIK ASIT", "FOLIC ACID", "FOLATE"],
        "default_unit": "ng/mL",
    },




    # CBC / hemogram
    "Hemoglobin": {
        "aliases": ["HEMOGLOBIN", "HGB", "HB"],
        "default_unit": "g/dL",
    },
    "Hematokrit": {
        "aliases": ["HEMATOKRIT", "HEMATOCRIT", "HCT"],
        "default_unit": "%",
    },
    "Eritrosit": {
        "aliases": ["ERITROSIT", "ERYTHROCYTE", "RBC"],
        "default_unit": "M/mm3",
    },
    "MCV": {
        "aliases": ["MCV"],
        "default_unit": "fL",
    },
    "MCH": {
        "aliases": ["MCH"],
        "default_unit": "pg",
    },
    "MCHC": {
        "aliases": ["MCHC"],
        "default_unit": "g/dL",
    },
    "RDW-CV": {
        "aliases": ["RDW-CV", "RDW CV", "RDW"],
        "default_unit": "%",
    },
    "Lökosit": {
        "aliases": ["LOKOSIT", "LOKOSİT", "WBC", "LEUKOCYTE"],
        "default_unit": "K/mm3",
    },




    # Absolute differentials
    "NOTROFIL_MUTLAK": {
        "aliases": ["PARCALI MUTLAK DEGERI", "PARCALI MUTLAK DEĞERİ", "NOTROFIL MUTLAK DEGERI", "NEUTROPHIL ABSOLUTE"],
        "default_unit": "K/mm3",
    },
    "Nötrofil %": {
        "aliases": ["PARCALI %", "NOTROFIL %", "NEUTROPHIL %", "NEU%"],
        "default_unit": "%",
    },
    "LENFOSIT_MUTLAK": {
        "aliases": ["LENFOSIT MUTLAK DEGERI", "LENFOSİT MUTLAK DEĞERİ", "LYMPHOCYTE ABSOLUTE"],
        "default_unit": "K/mm3",
    },
    "Lenfosit %": {
        "aliases": ["LENFOSIT %", "LENFOSİT %", "LYMPHOCYTE %", "LYM%"],
        "default_unit": "%",
    },
    "MONOSIT_MUTLAK": {
        "aliases": ["MONOSIT MUTLAK DEGERI", "MONOSİT MUTLAK DEĞERİ", "MONOCYTE ABSOLUTE"],
        "default_unit": "K/mm3",
    },
    "Monosit %": {
        "aliases": ["MONOSIT %", "MONOSİT %", "MONOCYTE %", "MONO%"],
        "default_unit": "%",
    },
    "EOZINOFIL_MUTLAK": {
        "aliases": ["EOZINOFIL MUTLAK DEGERI", "EOZİNOFİL MUTLAK DEĞERİ", "EOSINOPHIL ABSOLUTE"],
        "default_unit": "K/mm3",
    },
    "Eozinofil %": {
        "aliases": ["EOZINOFIL %", "EOZİNOFİL %", "EOSINOPHIL %", "EOS%"],
        "default_unit": "%",
    },
    "BAZOFIL_MUTLAK": {
        "aliases": ["BAZOFIL MUTLAK DEGERI", "BAZOFİL MUTLAK DEĞERİ", "BASOPHIL ABSOLUTE"],
        "default_unit": "K/mm3",
    },
    "Bazofil %": {
        "aliases": ["BAZOFIL %", "BAZOFİL %", "BASOPHIL %", "BAS%"],
        "default_unit": "%",
    },
    "Trombosit": {
        "aliases": ["TROMBOSIT", "TROMBOSİT", "PLATELET", "PLT"],
        "default_unit": "K/mm3",
    },
    "MPV": {
        "aliases": ["MPV"],
        "default_unit": "fL",
    },
    "PCT": {
        "aliases": ["PCT", "PLATELETCRIT"],
        "default_unit": "%",
    },
    "P_LCR": {
        "aliases": ["P-LCR (BUYUK TROMBOSITLERIN ORANI)", "P-LCR"],
        "default_unit": "%",
    },
    "IG Mutlak": {
        "aliases": [
            "IG MUTLAK",
            "IG ABSOLUTE",
            "IMMATURE GRANULOCYTE ABSOLUTE",
            "IMMATUR GRANULOSIT",
            "İMMATÜR GRANÜLOSİT",
            "IG (IMMATUR GRANULOSIT)",
            "IG (İMMATÜR GRANÜLOSİT)",
        ],
        "default_unit": "K/mm3",
    },
    "IG %": {
        "aliases": ["IG (IMMATUR GRANULOSIT) %", "IG (İMMATÜR GRANÜLOSİT) %"],
        "default_unit": "%",
    },
}








def _raise_pipeline_error(exc: ValueError) -> None:
    message = str(exc)
    if message == _PATIENT_NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from None
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from None



def _parse_patient_metadata_from_text(text: str) -> PatientMetadataOutput:
    """Extract display-only patient metadata from a text-based PDF report."""
    display_name = _extract_patient_display_name(text)

    joined_text = re.sub(r"\s+", " ", text).strip()
    folded_joined_text = _fold_patient_text(joined_text)

    birth_date, age, sex = _extract_patient_demographics(joined_text)

    if birth_date is None and age is None and sex is None:
        birth_date, age, sex = _extract_patient_demographics(
            folded_joined_text,
        )

    return PatientMetadataOutput(
        display_name=display_name,
        age=age,
        sex=sex,
        birth_date=birth_date,
    )


def _fold_patient_text(value: str) -> str:
    """Make Turkish/mojibake PDF text easier to match."""
    replacements = {
        "İ": "I",
        "I": "I",
        "ı": "i",
        "Ş": "S",
        "ş": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ü": "U",
        "ü": "u",
        "Ö": "O",
        "ö": "o",
        "Ç": "C",
        "ç": "c",
        "Ý": "I",
        "ý": "i",
        "Ð": "G",
        "ð": "g",
        "Þ": "S",
        "þ": "s",
        "Â": "A",
        "â": "a",
        "Ê": "E",
        "ê": "e",
        "Î": "I",
        "î": "i",
        "Ô": "O",
        "ô": "o",
        "Û": "U",
        "û": "u",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = value.replace(",", ".")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def _extract_patient_display_name(text: str) -> str | None:
    """Very tolerant patient-name extractor for lab report PDFs.

    It accepts:
    - Hastanın Adı, Soyadı EMİR CAN ALİ
    - Hastanin Adi. Soyadi EMIR CAN ALI
    - Hasta Ad Soyad EMIR CAN ALI
    - label on one line, name on following line
    - name between the label and TC Kimlik / D.Tarihi labels
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for index, line in enumerate(lines):
        for candidate_line in (line, _fold_patient_text(line)):
            if not _has_patient_name_label(candidate_line):
                continue

            candidate = _extract_name_after_label(candidate_line)

            if candidate is not None:
                return candidate

            # If the PDF placed the label alone, look at the next few lines.
            for next_line in lines[index + 1 : index + 6]:
                cleaned = _clean_patient_name_candidate(next_line)

                if cleaned is not None:
                    return cleaned

    joined_text = re.sub(r"\s+", " ", text).strip()
    folded_text = _fold_patient_text(joined_text)

    for candidate_text in (joined_text, folded_text):
        candidate = _extract_name_after_label(candidate_text)

        if candidate is not None:
            return candidate

    # Final fallback: if TC Kimlik exists, the name is usually immediately
    # before it after the patient-name label. This also catches weird spacing.
    tc_fallback = _extract_name_before_tc_label(folded_text)

    if tc_fallback is not None:
        return tc_fallback

    return None


def _has_patient_name_label(value: str) -> bool:
    folded = _fold_patient_text(value).lower()

    return (
        re.search(
            r"hasta\w*\W*ad\w*\W*soyad\w*",
            folded,
            flags=re.IGNORECASE,
        )
        is not None
    )


def _extract_name_after_label(value: str) -> str | None:
    folded = _fold_patient_text(value)

    label_match = re.search(
        r"hasta\w*\W*ad\w*\W*soyad\w*",
        folded,
        flags=re.IGNORECASE,
    )

    if label_match is None:
        return None

    tail = folded[label_match.end() :].strip(" .,:;-/\t")
    stop_match = re.search(
        r"\s*(?:tc\W*kimlik|t\W*c\W*kimlik|d\W*tarihi|dogum\W*tarihi|"
        r"dosya\W*numarasi|kayit\W*numarasi|kurumu|doktoru|"
        r"tetkik\W*istem|numune\W*alma|numune\W*kabul|uzman\W*onay|"
        r"tetkik\W*adi|sonuc|birim|referans)",
        tail,
        flags=re.IGNORECASE,
    )

    raw_candidate = tail[: stop_match.start()] if stop_match else tail

    return _clean_patient_name_candidate(raw_candidate)


def _extract_name_before_tc_label(folded_text: str) -> str | None:
    tc_match = re.search(r"\btc\W*kimlik\b", folded_text, flags=re.IGNORECASE)

    if tc_match is None:
        return None

    before_tc = folded_text[max(0, tc_match.start() - 180) : tc_match.start()]
    before_tc = re.sub(
        r".*hasta\w*\W*ad\w*\W*soyad\w*",
        "",
        before_tc,
        flags=re.IGNORECASE,
    )

    candidates = re.findall(
        r"\b[A-Z][A-Z']{1,}(?:\s+[A-Z][A-Z']{1,}){1,5}\b",
        before_tc,
    )

    for candidate in reversed(candidates):
        cleaned = _clean_patient_name_candidate(candidate)

        if cleaned is not None:
            return cleaned

    return None


def _clean_patient_name_candidate(value: str) -> str | None:
    cleaned = _fold_patient_text(value)
    cleaned = cleaned.strip(" .,:;-/\t")

    # PDF label residue cleanup:
    # Some reports leave the final letter of "Soyadi/Soyadı" at the beginning
    # of the extracted name, e.g. "i EMIR CAN ALI" or "I AFSIN ALI".
    cleaned = re.sub(r"^(?:i|I)\s+(?=[A-Z])", "", cleaned).strip(" .,:;-/\t")

    if not cleaned or cleaned == "-":
        return None

    stop_markers = [
        "TC Kimlik",
        "T C Kimlik",
        "D Tarihi",
        "Dogum Tarihi",
        "Dosya Numarasi",
        "Kayit Numarasi",
        "Kurumu",
        "Doktoru",
        "Tetkik Istem",
        "Numune Alma",
        "Numune Kabul",
        "Uzman Onay",
        "TETKIK ADI",
        "SONUC",
        "BIRIM",
        "REFERANS",
    ]

    lowered = cleaned.lower()

    for marker_text in stop_markers:
        marker_index = lowered.find(marker_text.lower())

        if marker_index >= 0:
            cleaned = cleaned[:marker_index].strip(" .,:;-/\t")
            lowered = lowered[:marker_index].strip(" .,:;-/\t")

    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-/\t")

    if not cleaned or len(cleaned) > 80:
        return None

    if any(char.isdigit() for char in cleaned):
        return None

    upper_cleaned = cleaned.upper()

    forbidden = [
        "TC KIMLIK",
        "D TARIHI",
        "DOSYA",
        "KAYIT",
        "KURUMU",
        "DOKTORU",
        "TETKIK",
        "NUMUNE",
        "UZMAN",
        "REFERANS",
        "SONUC",
        "BIRIM",
        "DUZEN",
        "SAGLIK",
        "LABORATUVAR",
    ]

    if any(marker in upper_cleaned for marker in forbidden):
        return None

    words = [word for word in re.split(r"\s+", cleaned) if word]

    if not 2 <= len(words) <= 6:
        return None

    return cleaned


def _extract_patient_demographics(
    text: str,
) -> tuple[date | None, int | None, str | None]:
    patterns = [
        r"d\W*tarihi\W*yasi\W*cinsiyeti\W+"
        r"(\d{2}\.\d{2}\.\d{4})\W*"
        r"(?:\((\d{1,3})\))?\W*([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"D\.?\s*Tarihi\s*\(Yaş[ıi]\)\s*/\s*Cinsiyeti\s+"
        r"(\d{2}\.\d{2}\.\d{4})\s*"
        r"(?:\((\d{1,3})\))?\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"D\.?\s*Tarihi\s*\(Yasi\)\s*/\s*Cinsiyeti\s+"
        r"(\d{2}\.\d{2}\.\d{4})\s*"
        r"(?:\((\d{1,3})\))?\s*/\s*([A-Za-zÇĞİÖŞÜçğıöşü]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match is None:
            continue

        birth_date = _parse_turkish_date(match.group(1))
        age_text = match.group(2)
        age = int(age_text) if age_text is not None else None
        sex = _normalize_patient_sex(match.group(3))

        return birth_date, age, sex

    return None, None, None


def _parse_turkish_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        return None


def _normalize_patient_sex(value: str) -> str:
    normalized = _fold_patient_text(value).strip().lower()

    if normalized.startswith("erkek") or normalized.startswith("male"):
        return "Male"

    if normalized.startswith("kadin") or normalized.startswith("female"):
        return "Female"

    return value.strip()








@router.post("/mock", response_model=AnalysisPipelineResult, status_code=status.HTTP_201_CREATED)
async def analyze_mock_report(
    payload: MockLabReportInput,
    pipeline: AnalysisPipelineDep,
) -> AnalysisPipelineResult:
    if payload.patient_id == DEMO_PATIENT_ID:
        await _ensure_demo_patient_and_user()


    try:
        return await pipeline.run(payload)
    except ValueError as exc:
        _raise_pipeline_error(exc)








@router.post("/upload", response_model=AnalysisPipelineResult, status_code=status.HTTP_201_CREATED)
async def analyze_uploaded_pdf_report(
    pipeline: AnalysisPipelineDep,
    file: UploadFile = File(...),
) -> AnalysisPipelineResult:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a filename.")




    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF files are supported for this demo upload flow.")




    file_bytes = await file.read()




    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded PDF is empty.")




    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Uploaded PDF is too large. Maximum size is 10 MB.")




    extracted_text = _extract_text_from_pdf(file_bytes)
    patient_metadata = _parse_patient_metadata_from_text(extracted_text)




    if not extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No selectable text could be extracted from this PDF. Scanned/image PDFs need OCR.",
        )




    values = _parse_lab_values_from_text(extracted_text, patient_sex=patient_metadata.sex)




    if not values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No supported lab values could be parsed from this PDF.")




    await _ensure_demo_patient_and_user()




    payload = MockLabReportInput(
        patient_id=DEMO_PATIENT_ID,
        uploaded_by_user_id=DEMO_UPLOADED_BY_USER_ID,
        file_name=file.filename,
        # Labelled document dates only; never the upload day.
        report_date=_document_report_date(extracted_text),
        values=values,
    )




    try:
        result = await pipeline.run(payload)
        return result.model_copy(update={"patient": patient_metadata})
    except ValueError as exc:
        _raise_pipeline_error(exc)








def _document_report_date(text: str) -> date | None:
    from app.domain.document_dates import extract_document_dates

    dates = extract_document_dates(text)
    for key in ("specimen_date", "event_date", "result_date", "document_date"):
        if key in dates:
            return dates[key]
    return None


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PDF parser dependency is missing. Install it with: pip install pypdf python-multipart",
        ) from exc




    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except PrivacyViolation:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"PDF text extraction failed: {exc}") from exc








# One-sided report limits ("< 200", "> 40") reach the legacy RuleEngine with a
# distant opposite bound. These are open-interval sentinels, not clinical values;
# a lone number without a printed comparator is never turned into a limit.
_OPEN_LOWER_SENTINEL = -1_000_000_000.0
_OPEN_UPPER_SENTINEL = 1_000_000_000.0

_LEGACY_NUM = r"\d{1,3}(?:\.\d{3})+(?![\d.])|\d+(?:\.\d+)?"
_VALUE_TOKEN = re.compile(rf"(?P<op><=|>=|<|>)?\s*(?P<num>[-+]?(?:{_LEGACY_NUM}))")
_LEADING_FLAG = re.compile(
    r"^(?:\(\s*(?:HH|LL|H|L|Y|D)\s*\)|(?:HH|LL|HIGH|LOW|H|L|Y|D)(?![A-Za-z/0-9])|\*+|[↑↓]+)\s*",
    flags=re.IGNORECASE,
)
_REFERENCE_RANGE_IN_TEXT = re.compile(
    rf"\(?\s*[-+]?(?:{_LEGACY_NUM})\s*-\s*[-+]?(?:{_LEGACY_NUM})\s*\)?"
)
_REFERENCE_LIMIT_IN_TEXT = re.compile(rf"(?:<=|>=|<|>)\s*(?:{_LEGACY_NUM})")
_SEX_REFERENCE_HINT = re.compile(r"(?i)\b(?:erkek|kadin|male|female)\b|(?<![A-Za-z])[EK]\s*:")
_PREVIOUS_RESULT_DATE = re.compile(r"\(?\b\d{2}\.\d{2}\.\d{4}\b\)?")


def _parse_lab_values_from_text(text: str, patient_sex: str | None = None) -> list[dict[str, Any]]:
    """Read one row per known parameter, using only what the line prints.

    The reference printed on the row is preserved as ``reference_text`` and
    parsed into bounds; nothing is substituted from demo or catalogue ranges.
    ``measured_at`` stays empty: document dates are attached by the caller.
    """
    normalized_text = _normalize_text(text)
    lines = [
        line.strip()
        for line in normalized_text.splitlines()
        if line.strip() and not _is_noise_line(line)
    ]

    parsed_values: list[dict[str, Any]] = []
    for raw_parameter_name, config in LAB_PARAMETER_ALIASES.items():
        parsed_value = _find_parameter_value_in_lines(
            raw_parameter_name=raw_parameter_name,
            aliases=config["aliases"],
            default_unit=config["default_unit"],
            lines=lines,
            patient_sex=patient_sex,
        )
        if parsed_value is not None:
            parsed_values.append(parsed_value)
    return parsed_values


def _is_bun_creatinine_ratio_line(line: str) -> bool:
    normalized = _normalize_text(line).upper().replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "BUN/KREATININ",
            "BUN/CREATININE",
            "BUNCREATININERATIO",
        )
    )


def _row_quality(row: dict[str, Any]) -> tuple[int, int]:
    return (1 if row.get("reference_parsed") else 0, 1 if row.get("unit_from_source") else 0)


def _find_parameter_value_in_lines(
    *,
    raw_parameter_name: str,
    aliases: list[str],
    default_unit: str,
    lines: list[str],
    patient_sex: str | None = None,
) -> dict[str, Any] | None:
    """Return the best source row for a parameter.

    A report can mention the same marker more than once (summary, previous
    result, the table row). The row that carries a usable printed reference and
    unit wins; ties keep document order.
    """
    sorted_aliases = sorted(aliases, key=len, reverse=True)
    best: dict[str, Any] | None = None

    for line in lines:
        if raw_parameter_name in {"BUN", "Kreatinin"} and _is_bun_creatinine_ratio_line(line):
            continue
        for alias in sorted_aliases:
            if not _line_contains_alias(line, alias):
                continue
            parsed = _parse_result_row(line, alias, raw_parameter_name, default_unit, patient_sex=patient_sex)
            if parsed is None:
                continue
            if parsed["normalized_value"] is not None and not _looks_like_reasonable_value(
                raw_parameter_name, parsed["normalized_value"]
            ):
                continue
            if best is None or _row_quality(parsed) > _row_quality(best):
                best = parsed
            break
        if best is not None and _row_quality(best) == (1, 1):
            break

    if best is None:
        return None
    best.pop("reference_parsed", None)
    best.pop("unit_from_source", None)
    return best


def _reference_text_from_tail(text: str) -> str | None:
    """Locate the printed reference after the value/unit columns."""
    text = _PREVIOUS_RESULT_DATE.sub(" ", text).replace("↓", " ").replace("↑", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None
    sex_hint = _SEX_REFERENCE_HINT.search(text)
    if sex_hint:
        start = min(
            (m.start() for m in (re.search(r"[<>]?=?\s*[-+]?\d", text), sex_hint) if m is not None),
            default=sex_hint.start(),
        )
        return text[start:].strip()
    ranges = list(_REFERENCE_RANGE_IN_TEXT.finditer(text))
    if ranges:
        return ranges[-1].group(0).strip()
    limits = list(_REFERENCE_LIMIT_IN_TEXT.finditer(text))
    if limits:
        return limits[-1].group(0).strip()
    if re.search(r"(?i)\b(negatif|negative|pozitif|positive)\b", text):
        return re.search(r"(?i)\b(negatif|negative|pozitif|positive)\b", text).group(0)
    return None


def _parse_result_row(
    line: str,
    alias: str,
    parameter_name: str,
    default_unit: str,
    *,
    patient_sex: str | None = None,
) -> dict[str, Any] | None:
    from app.domain.lab_result_classification import (
        _mixed_grouping,
        _number,
        is_count_per_volume_unit,
        parse_source_reference,
    )

    alias_match = _find_alias_match(line, alias)
    if alias_match is None:
        return None

    after_alias = line[alias_match.end():].strip()
    value_match = _VALUE_TOKEN.search(after_alias)
    if value_match is None:
        return None

    after_value = after_alias[value_match.end():].strip()
    after_value = re.sub(r"^(?:[:=]|\s)+", "", after_value).strip()
    source_flag = None
    flag_match = _LEADING_FLAG.match(after_value)
    if flag_match:
        source_flag = flag_match.group(0).strip()
        after_value = after_value[flag_match.end():].strip()

    unit_match = _match_unit(after_value)
    unit = unit_match.group(0) if unit_match is not None else default_unit
    after_unit = after_value[unit_match.end():].strip() if unit_match is not None else after_value

    reference_text = _reference_text_from_tail(after_unit)
    reference_tokens = re.findall(rf"{_LEGACY_NUM}", reference_text or "")
    grouped = is_count_per_volume_unit(unit) or _mixed_grouping(value_match.group("num"), *reference_tokens)
    number = _number(value_match.group("num"), grouped_thousands=grouped)
    if number is None:
        return None
    value = float(number)
    comparator = value_match.group("op")

    reference_min = reference_max = None
    reference_parsed = False
    if reference_text:
        reference = parse_source_reference(
            reference_text,
            unit=unit if unit_match is not None else None,
            patient_sex=patient_sex,
            grouped_thousands=grouped,
        )
        if not reference.error:
            reference_parsed = True
            reference_min = float(reference.low) if reference.low is not None else None
            reference_max = float(reference.high) if reference.high is not None else None

    extracted_min, extracted_max = reference_min, reference_max
    if extracted_min is not None and extracted_max is None:
        extracted_max = _OPEN_UPPER_SENTINEL
    elif extracted_max is not None and extracted_min is None:
        extracted_min = _OPEN_LOWER_SENTINEL

    if reference_text and _SEX_REFERENCE_HINT.search(reference_text):
        # The canonical row keeps the full sex-specific text; the deterministic
        # classifier selects the row from the case's patient sex.
        reference_min = reference_max = None
    raw_value = f"{comparator}{value_match.group('num')}" if comparator else value_match.group("num")
    return {
        "raw_parameter_name": parameter_name,
        "raw_value": raw_value,
        # A censored value ("<0.5") is not an exact measurement.
        "normalized_value": None if comparator else value,
        # Only a printed unit is a source unit; the catalogue default is kept
        # for the legacy reference resolver in ``extracted_unit`` alone.
        "unit": unit if unit_match is not None else None,
        "reference_text": reference_text,
        "reference_min": reference_min,
        "reference_max": reference_max,
        "extracted_reference_min": extracted_min,
        "extracted_reference_max": extracted_max,
        "extracted_unit": unit,
        "measured_at": None,
        "value_type": "censored" if comparator else "numeric",
        "source_flag": source_flag,
        "confidence": 0.97 if reference_parsed and unit_match is not None else 0.9,
        "needs_review": not reference_parsed or comparator is not None,
        "reference_parsed": reference_parsed,
        "unit_from_source": unit_match is not None,
    }


def _match_unit(text: str) -> re.Match[str] | None:
    unit_patterns = [
        r"mL/dk/1\.73\s?m\^?2",
        r"mL/min/1\.73\s?m\^?2",
        r"x?10\^3/uL",
        r"x?10\^6/uL",
        r"x?10\^9/L",
        r"x?10\^12/L",
        r"x?10\^3/mm3",
        r"x?10\^6/mm3",
        r"K/mm3",
        r"M/mm3",
        r"K/uL",
        r"M/uL",
        r"K/mm",
        r"M/mm",
        r"(?:hucre|cells?|adet)/uL",
        r"/mm3",
        r"/uL",
        r"uIU/mL",
        r"mIU/mL",
        r"mIU/L",
        r"mU/L",
        r"IU/mL",
        r"IU/L",
        r"U/mL",
        r"U/L",
        r"mmol/L",
        r"umol/L",
        r"pmol/L",
        r"nmol/L",
        r"mEq/L",
        r"mg/dL",
        r"ug/dL",
        r"g/dL",
        r"ng/dL",
        r"ng/mL",
        r"pg/mL",
        r"ug/L",
        r"ng/L",
        r"mg/L",
        r"g/L",
        r"mm/saat",
        r"mm/sa",
        r"mm/h",
        r"mm/S",
        r"fL",
        r"pg",
        r"%",
    ]
    return re.match("(" + "|".join(unit_patterns) + r")(?![A-Za-z0-9])", text, flags=re.IGNORECASE) or re.match(
        r"%", text
    )


def _normalize_text(text: str) -> str:
    # "10³/µL" must stay a power of ten, not become "103/uL".
    text = re.sub(
        r"10([⁰¹²³⁴⁵⁶⁷⁸⁹]+)",
        lambda m: "10^" + m.group(1).translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")),
        text,
    )
    replacements = {
        "İ": "I",
        "ı": "i",
        "Ş": "S",
        "ş": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ü": "U",
        "ü": "u",
        "Ö": "O",
        "ö": "o",
        "Ç": "C",
        "ç": "c",
        "µ": "u",
        "μ": "u",
        "–": "-",
        "—": "-",
        "−": "-",
        "×": "x",
        "∙": ".",
        "³": "3",
        "²": "2",
        "≤": "<=",
        "≥": ">=",
        "\t": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Turkish "1.234,5" -> "1234.5"; decimal comma "3,5" -> "3.5".
    text = re.sub(
        r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+),(\d+)(?![\d.,])",
        lambda m: m.group(1).replace(".", "") + "." + m.group(2),
        text,
    )
    text = text.replace(",", ".")
    text = re.sub(r"[ ]{2,}", " ", text)
    return text


def _is_noise_line(line: str) -> bool:
    upper = line.upper()




    noise_markers = [
        "KREATININ. IDRAR7890123456789012345",
        "KREATININ, IDRAR7890123456789012345",
        "QSONUC",
        "QRAPORNOTU",
        "Q_CALISILDIGI_YER",
        "QREF",
        "QONCEKI",
        "QDL",
        "QIRIM",
        "QRLABEL",
        "GUID:",
        "IP:",
        "MAC:",
        "SAYFA:",
        "TETKIK ADI SONUC BIRIM ONCEKI SONUC",
        "TETKIK ADI",
        "REFERANS ARALIK",
        "KARAR SINIRI",
        "DURUM NOTU",
        "DUZEN SAGLIK",
        "TIBBI LABORATUVAR",
        "HASTANIN ADI",
        "TC KIMLIK",
        "D.TARIHI",
        "DOSYA NUMARASI",
        "KAYIT NUMARASI",
        "NUMUNE",
        "UZMAN ONAY",
        "BU BELGE",
        "DP-KYF",
        "UST ISARETLER",
        "OZEL ISARETLER",
        "AKREDITE",
        "WWW.",
    ]




    return any(marker.upper() in upper for marker in noise_markers)








def _line_contains_alias(line: str, alias: str) -> bool:
    alias = _normalize_text(alias)
    escaped_alias = re.escape(alias)
    pattern = rf"(?<![A-Za-z0-9]){escaped_alias}(?![A-Za-z0-9])"
    return re.search(pattern, line, flags=re.IGNORECASE) is not None








def _find_alias_match(line: str, alias: str) -> re.Match[str] | None:
    alias = _normalize_text(alias)
    escaped_alias = re.escape(alias)
    pattern = rf"(?<![A-Za-z0-9]){escaped_alias}(?![A-Za-z0-9])"
    return re.search(pattern, line, flags=re.IGNORECASE)








def _looks_like_reasonable_value(parameter_name: str, value: float) -> bool:
    if value < 0:
        return False




    upper = parameter_name.upper()




    if upper in {"KREATININ", "CREATININE"} and value > 50:
        return False




    if "VITAMIN D" in upper and value > 300:
        return False




    if upper in {"TSH", "FT3", "FT4"} and value > 500:
        return False




    return True