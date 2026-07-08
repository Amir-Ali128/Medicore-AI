"""Seed minimal demo users and one patient profile for local/dev use.

Creates (or reuses) one doctor user, one patient user, and one patient profile.
Idempotent by deterministic email / external_ref. Uses safe fake data only, no
lab results, no medical content. Commits on success, rolls back on error.

Run:  python -m app.scripts.seed_demo_data
"""

from __future__ import annotations

import asyncio
from datetime import date

from sqlalchemy import select

from app.domain.enums import Sex, UserRole
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import AsyncSessionFactory, engine

DOCTOR_EMAIL = "doctor@medicore.local"
PATIENT_EMAIL = "patient@medicore.local"
DEMO_PATIENT_EXTERNAL_REF = "demo-patient"

# Placeholder, intentionally non-usable for login (no auth in Phase 1).
_SEED_PASSWORD_HASH = "seed$disabled$not-for-login"


async def _get_or_create_user(
    session, *, email: str, full_name: str, role: UserRole
) -> tuple[User, bool]:
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    user = User(
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=_SEED_PASSWORD_HASH,
        is_active=True,
    )
    session.add(user)
    return user, True


async def _get_or_create_patient(
    session, *, external_ref: str, patient_user: User
) -> tuple[Patient, bool]:
    existing = (
        await session.execute(
            select(Patient).where(Patient.external_ref == external_ref)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    patient = Patient(
        external_ref=external_ref,
        sex=Sex.MALE,
        date_of_birth=date(1990, 5, 15),
        is_pregnant=False,
        metadata_json={"seed": True, "patient_user_email": patient_user.email},
    )
    session.add(patient)
    return patient, True


async def _seed() -> None:
    async with AsyncSessionFactory() as session:
        try:
            doctor, doctor_created = await _get_or_create_user(
                session, email=DOCTOR_EMAIL, full_name="Demo Doctor", role=UserRole.DOCTOR
            )
            patient_user, patient_user_created = await _get_or_create_user(
                session, email=PATIENT_EMAIL, full_name="Demo Patient", role=UserRole.PATIENT
            )
            await session.flush()

            patient, patient_created = await _get_or_create_patient(
                session, external_ref=DEMO_PATIENT_EXTERNAL_REF, patient_user=patient_user
            )
            await session.flush()

            await session.commit()
        except Exception:
            await session.rollback()
            raise

        def _tag(created: bool) -> str:
            return "created" if created else "reused"

        print(f"doctor_user_id={doctor.id} ({_tag(doctor_created)})")
        print(f"patient_user_id={patient_user.id} ({_tag(patient_user_created)})")
        print(f"patient_id={patient.id} ({_tag(patient_created)})")

    await engine.dispose()


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
