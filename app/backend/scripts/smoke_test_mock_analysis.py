"""End-to-end smoke test for the mock analysis flow (no HTTP, no AI).

Builds all repositories and services manually and runs the AnalysisPipeline
against a small set of fake Phase 1 lab values for the seeded demo patient.

Assumes these setup steps have already been run:
    1. python -m app.scripts.create_dev_tables
    2. python -m app.scripts.import_reference_csv
    3. python -m app.scripts.seed_demo_data

If required data is missing, a clear ValueError explains which step to run.

Run:  python -m app.scripts.smoke_test_mock_analysis
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.domain.alias_engine import AliasEngine
from app.domain.analysis_pipeline import AnalysisPipeline
from app.domain.reference_resolver import ReferenceResolver
from app.domain.rule_engine import RuleEngine
from app.domain.trend_engine import TrendEngine
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.infrastructure.database.repositories.analysis_run_repository import (
    AnalysisRunRepository,
)
from app.infrastructure.database.repositories.clinical_parameter_repository import (
    ClinicalParameterRepository,
)
from app.infrastructure.database.repositories.lab_report_repository import (
    LabReportRepository,
)
from app.infrastructure.database.repositories.lab_result_repository import (
    LabResultRepository,
)
from app.infrastructure.database.repositories.parameter_alias_repository import (
    ParameterAliasRepository,
)
from app.infrastructure.database.repositories.reference_range_repository import (
    ReferenceRangeRepository,
)
from app.infrastructure.database.session import AsyncSessionFactory, engine
from app.schemas.lab_analysis import MockLabReportInput, RawLabValue

DOCTOR_EMAIL = "doctor@medicore.local"
PATIENT_EMAIL = "patient@medicore.local"
DEMO_PATIENT_EXTERNAL_REF = "demo-patient"


def _build_payload(patient_id, uploaded_by_user_id) -> MockLabReportInput:
    today = date.today()
    values = [
        RawLabValue(
            raw_parameter_name="Hemoglobin",
            raw_value="13.5",
            normalized_value=Decimal("13.5"),
            unit="g/dL",
            extracted_reference_min=Decimal("13.0"),
            extracted_reference_max=Decimal("17.0"),
            extracted_unit="g/dL",
            measured_at=today,
        ),
        RawLabValue(
            raw_parameter_name="Ferritin",
            raw_value="8",
            normalized_value=Decimal("8"),
            unit="ng/mL",
            extracted_reference_min=Decimal("30"),
            extracted_reference_max=Decimal("400"),
            extracted_unit="ng/mL",
            measured_at=today,
        ),
        RawLabValue(
            raw_parameter_name="HbA1c",
            raw_value="6.2",
            normalized_value=Decimal("6.2"),
            unit="%",
            extracted_reference_min=Decimal("4.0"),
            extracted_reference_max=Decimal("5.6"),
            extracted_unit="%",
            measured_at=today,
        ),
        RawLabValue(
            raw_parameter_name="TSH",
            raw_value="2.5",
            normalized_value=Decimal("2.5"),
            unit="mIU/L",
            extracted_reference_min=Decimal("0.4"),
            extracted_reference_max=Decimal("4.0"),
            extracted_unit="mIU/L",
            measured_at=today,
        ),
        RawLabValue(
            raw_parameter_name="ALT",
            raw_value="30",
            normalized_value=Decimal("30"),
            unit="U/L",
            extracted_reference_min=Decimal("7"),
            extracted_reference_max=Decimal("56"),
            extracted_unit="U/L",
            measured_at=today,
        ),
    ]
    return MockLabReportInput(
        patient_id=patient_id,
        uploaded_by_user_id=uploaded_by_user_id,
        file_name="smoke_test.json",
        report_date=today,
        values=values,
    )


async def _smoke() -> None:
    async with AsyncSessionFactory() as session:
        # 0) Validate setup / data presence.
        try:
            patient_user = (
                await session.execute(select(User).where(User.email == PATIENT_EMAIL))
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise ValueError(
                "Database tables are missing. Run: python -m app.scripts.create_dev_tables"
            ) from exc

        if patient_user is None:
            raise ValueError(
                "Demo patient user missing. Run: python -m app.scripts.seed_demo_data"
            )

        patient = (
            await session.execute(
                select(Patient).where(Patient.external_ref == DEMO_PATIENT_EXTERNAL_REF)
            )
        ).scalar_one_or_none()
        if patient is None:
            raise ValueError(
                "Demo patient profile missing. Run: python -m app.scripts.seed_demo_data"
            )

        parameter_repository = ClinicalParameterRepository(session)
        if await parameter_repository.get_by_code("HGB") is None:
            raise ValueError(
                "Reference parameters missing. Run: python -m app.scripts.import_reference_csv"
            )

        doctor = (
            await session.execute(select(User).where(User.email == DOCTOR_EMAIL))
        ).scalar_one_or_none()

        # 1) Build repositories and services manually.
        alias_repository = ParameterAliasRepository(session)
        reference_range_repository = ReferenceRangeRepository(session)
        lab_report_repository = LabReportRepository(session)
        lab_result_repository = LabResultRepository(session)
        analysis_run_repository = AnalysisRunRepository(session)

        pipeline = AnalysisPipeline(
            session,
            alias_engine=AliasEngine(parameter_repository, alias_repository),
            reference_resolver=ReferenceResolver(
                reference_range_repository, parameter_repository
            ),
            rule_engine=RuleEngine(),
            trend_engine=TrendEngine(),
            lab_report_repository=lab_report_repository,
            lab_result_repository=lab_result_repository,
            analysis_run_repository=analysis_run_repository,
            parameter_repository=parameter_repository,
        )

        # 2) Run the pipeline.
        payload = _build_payload(patient.id, doctor.id if doctor else None)
        result = await pipeline.run(payload)

    # 3) Report (no diagnosis, no advice).
    print(f"analysis_run_id={result.analysis_run_id}")
    print(f"lab_report_id={result.lab_report_id}")
    counts = result.counts
    print(
        "counts: "
        f"total={counts.total} normal={counts.normal} low={counts.low} "
        f"high={counts.high} needs_review={counts.needs_review} unknown={counts.unknown}"
    )
    print("results:")
    for item in result.results:
        print(
            f"  {item.raw_parameter_name} | {item.parameter_code} | "
            f"{item.result_status.value} | {item.trend_status.value} | "
            f"needs_review={item.needs_review}"
        )

    await engine.dispose()


def main() -> None:
    asyncio.run(_smoke())


if __name__ == "__main__":
    main()
