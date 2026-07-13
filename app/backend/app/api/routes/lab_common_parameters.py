"""Activate commonly requested laboratory parameters for the Phase 1 PDF flow.

This module extends the existing parser aliases and Render bootstrap without
changing the core pipeline.  Reference intervals continue to prefer the
laboratory report and then the canonical CSV reference data.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text as sql_text

from app.api.routes import lab_analysis


COMMON_PARAMETERS: dict[str, dict[str, Any]] = {
    "HbA1c": {
        "code": "HBA1C",
        "unit": "%",
        "aliases": ["HBA1C", "HB A1C", "HEMOGLOBIN A1C", "GLIKE HEMOGLOBIN", "GLİKE HEMOGLOBİN"],
    },
    "Sodyum": {
        "code": "SODYUM",
        "unit": "mmol/L",
        "aliases": ["SODYUM", "SODIUM", "NA", "NA+"],
    },
    "Potasyum": {
        "code": "POTASYUM",
        "unit": "mmol/L",
        "aliases": ["POTASYUM", "POTASSIUM", "K", "K+"],
    },
    "Klor": {
        "code": "KLOR",
        "unit": "mmol/L",
        "aliases": ["KLOR", "KLORUR", "KLORÜR", "CHLORIDE", "CL", "CL-"],
    },
    "Kalsiyum": {
        "code": "KALSIYUM",
        "unit": "mg/dL",
        "aliases": ["KALSIYUM", "KALSİYUM", "CALCIUM", "CA", "TOTAL KALSIYUM", "TOTAL KALSİYUM"],
    },
    "Magnezyum": {
        "code": "MAGNEZYUM",
        "unit": "mg/dL",
        "aliases": ["MAGNEZYUM", "MAGNESIUM", "MG"],
    },
    "Fosfor": {
        "code": "FOSFOR",
        "unit": "mg/dL",
        "aliases": ["FOSFOR", "PHOSPHORUS", "PHOSPHATE", "P"],
    },
    "Ürik Asit": {
        "code": "URIK_ASIT",
        "unit": "mg/dL",
        "aliases": ["URIK ASIT", "ÜRİK ASİT", "URIC ACID", "URATE"],
    },
    "Albumin": {
        "code": "ALBUMIN",
        "unit": "g/dL",
        "aliases": ["ALBUMIN", "ALBÜMİN", "ALBUMİN", "ALB"],
    },
    "Total Protein": {
        "code": "TOTAL_PROTEIN",
        "unit": "g/dL",
        "aliases": ["TOTAL PROTEIN", "TOTAL PROTEİN", "TOPLAM PROTEIN", "TOPLAM PROTEİN"],
    },
    "İndirekt Bilirubin": {
        "code": "INDIREKT_BILIRUBIN",
        "unit": "mg/dL",
        "aliases": ["INDIREKT BILIRUBIN", "İNDİREKT BİLİRUBİN", "INDIRECT BILIRUBIN", "BILIRUBIN INDIRECT"],
    },
    "LDH": {
        "code": "LDH",
        "unit": "U/L",
        "aliases": ["LDH", "LAKTAT DEHIDROGENAZ", "LAKTAT DEHİDROGENAZ", "LACTATE DEHYDROGENASE"],
    },
    "Ferritin": {
        "code": "FERRITIN",
        "unit": "ng/mL",
        "aliases": ["FERRITIN", "FERRİTİN"],
    },
    "Serum Demiri": {
        "code": "SERUM_DEMIRI",
        "unit": "ug/dL",
        "aliases": ["SERUM DEMIRI", "SERUM DEMİRİ", "DEMIR", "DEMİR", "IRON", "SERUM IRON"],
    },
    "TDBK": {
        "code": "TDBK",
        "unit": "ug/dL",
        "aliases": ["TDBK", "TOTAL DEMIR BAGLAMA KAPASITESI", "TOTAL DEMİR BAĞLAMA KAPASİTESİ", "TIBC"],
    },
    "Transferrin": {
        "code": "TRANSFERRIN",
        "unit": "mg/dL",
        "aliases": ["TRANSFERRIN", "TRANSFERRİN"],
    },
    "Transferrin Satürasyonu": {
        "code": "TRANSFERRIN_SATURASYONU",
        "unit": "%",
        "aliases": ["TRANSFERRIN SATURASYONU", "TRANSFERRİN SATÜRASYONU", "TRANSFERRIN SATURATION", "TSAT"],
    },
    "Prokalsitonin": {
        "code": "PROKALSITONIN",
        "unit": "ng/mL",
        "aliases": ["PROKALSITONIN", "PROKALSİTONİN", "PROCALCITONIN", "PCT PROKALSITONIN"],
    },
    "Troponin": {
        "code": "TROPONIN",
        "unit": "ng/L",
        "aliases": ["TROPONIN", "TROPONİN", "TROPONIN I", "TROPONİN I", "TROPONIN T", "HS-TROPONIN", "HS TROPONIN"],
    },
    "CK-MB": {
        "code": "CK_MB",
        "unit": "ng/mL",
        "aliases": ["CK-MB", "CK MB", "CKMB", "CREATINE KINASE-MB", "KREATIN KINAZ MB", "KREATİN KİNAZ MB"],
    },
}


for canonical_name, config in COMMON_PARAMETERS.items():
    lab_analysis.LAB_PARAMETER_ALIASES.setdefault(
        canonical_name,
        {
            "aliases": config["aliases"],
            "default_unit": config["unit"],
        },
    )


_original_ensure_parameters = lab_analysis._ensure_render_demo_clinical_parameters


async def _ensure_parameters_with_common_panel(session: Any) -> None:
    await _original_ensure_parameters(session)

    for canonical_name, config in COMMON_PARAMETERS.items():
        parameter_code = str(config["code"])
        default_unit = str(config["unit"])
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
                        id, parameter_code, canonical_name, default_unit,
                        active_phase1, analysis_level, metadata_json,
                        created_at, updated_at
                    )
                    VALUES (
                        :id, :parameter_code, :canonical_name, :default_unit,
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
                        '{"source":"common_panel_bootstrap"}'::jsonb,
                        NOW(), NOW()
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"medicore-common:{parameter_code}")),
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
                    SET parameter_code = :parameter_code,
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


lab_analysis._ensure_render_demo_clinical_parameters = _ensure_parameters_with_common_panel
