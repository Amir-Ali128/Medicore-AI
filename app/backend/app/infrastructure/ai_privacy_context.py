"""Request-scoped DB identifiers. Never add clinical notes as identity tokens."""
from __future__ import annotations
from collections.abc import AsyncIterator
import asyncio
from datetime import date
import uuid

from fastapi import Request
from app.api.dependencies import SessionDep
from app.domain.privacy_gateway import PrivacyViolation, KnownIdentifier, age_in_years
from app.infrastructure.ai_privacy_client import PrivacyContext, context
from app.infrastructure.database.models.patient import Patient

_IDENTITY_FIELDS = frozenset({
    'name','patient_name','full_name','first_name','last_name','surname','given_name','family_name',
    'tckn','national_id','national_identity_number','phone','telephone','mobile','email','address',
    'date_of_birth','birth_date','dob','external_ref','protocol_no',
})


async def load_patient_identifiers(session, patient_id: uuid.UUID) -> PrivacyContext:
    patient=await session.get(Patient,patient_id)
    if patient is None: raise PrivacyViolation()
    identifiers=[KnownIdentifier(str(patient_id),'KAYIT_NO')]
    def identity(value, field):
        category={'tckn':'TCKN','national_id':'TCKN','national_identity_number':'TCKN',
                  'phone':'TELEFON','telephone':'TELEFON','mobile':'TELEFON','email':'EPOSTA',
                  'address':'ADRES','date_of_birth':'DOGUM_TARIHI','birth_date':'DOGUM_TARIHI','dob':'DOGUM_TARIHI',
                  'external_ref':'KAYIT_NO','protocol_no':'KAYIT_NO'}.get(field,'HASTA_ADI')
        return KnownIdentifier(str(value),category)
    for field in _IDENTITY_FIELDS:
        value=getattr(patient,field,None)
        if value: identifiers.append(identity(value,field))
    def collect(value, container="root"):
        if not isinstance(value,dict): return
        for field,item in value.items():
            if field.casefold() in _IDENTITY_FIELDS and (field.casefold()!='name' or container in ('root','identity','patient','demographics','profile')) and isinstance(item,(str,int)) and not isinstance(item,bool):
                identifiers.append(identity(item,field.casefold()))
            elif isinstance(item,dict): collect(item,field.casefold())
    collect(patient.metadata_json or {})
    born=getattr(patient,'date_of_birth',None)
    if born:
        identifiers.extend(KnownIdentifier(value,'DOGUM_TARIHI') for value in (born.isoformat(),born.strftime('%d.%m.%Y'),born.strftime('%d/%m/%Y')))
    age=age_in_years(born) if born else None
    return PrivacyContext(str(patient_id),tuple(dict.fromkeys(identifiers)),age)


async def privacy_request_context(request: Request, session: SessionDep) -> AsyncIterator[None]:
    """Global FastAPI dependency, also covering legacy routers if re-enabled."""
    from app.domain.patient_scope import source_references, SOURCE_MODELS
    from app.infrastructure.database.models.doctor_review import DoctorReview
    from app.infrastructure.database.models.clinical_hypothesis import ClinicalHypothesis
    metadata=[request.path_params,dict(request.query_params)]
    if request.headers.get('content-type','').startswith('application/json'):
        try: metadata.append(await request.json())
        except ValueError: pass
    elif 'multipart/form-data' in request.headers.get('content-type',''):
        form=await request.form()
        metadata.append({key:value for key,value in form.items() if isinstance(value,str)})
    # Resolve only on the first actual provider attempt. Read-only/non-AI routes
    # retain their original access checks and error codes; concurrent readers share
    # one load, never concurrent operations on the request's SQLAlchemy session.
    cached: PrivacyContext | None = None
    lock=asyncio.Lock()
    async def resolve() -> PrivacyContext:
        nonlocal cached
        async with lock:
            if cached is not None: return cached
            references=set(source_references(metadata))
            patient_ids={value for key,value in references if key=='patient'}
            for key,value in references:
                if key=='patient': continue
                record=await session.get(SOURCE_MODELS[key],value)
                if isinstance(record,DoctorReview):
                    record=await session.get(ClinicalHypothesis,record.clinical_hypothesis_id)
                if record is not None: patient_ids.add(record.patient_id)
            if len(patient_ids)>1: raise PrivacyViolation()
            cached=await load_patient_identifiers(session,next(iter(patient_ids))) if patient_ids else PrivacyContext()
            return cached
    current=PrivacyContext(loader=resolve)
    token=context.set(current)
    try: yield
    finally: context.reset(token)
