"""The only permitted provider-send and base64-encoding boundary.

All retries/fallbacks use this boundary. ContextVars isolate concurrent requests;
raw media cannot reach the SDK and identifiers never enter audit records.
"""
from __future__ import annotations

import asyncio
import base64
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import re
from typing import Any

from app.domain.privacy_gateway import (
    PrivacyViolation, _sanitize_image, _sanitize_pdf, age_in_years,
    final_leak_check, sanitize_text, valid_tckn,
)

logger=logging.getLogger('medicore.privacy.audit')


@dataclass(frozen=True)
class PrivacyContext:
    patient_id: str | None = None
    known_identifiers: tuple[str,...] = ()
    age: int | None = None
    loader: Callable[[], Awaitable[PrivacyContext]] | None = None


context: ContextVar[PrivacyContext] = ContextVar('ai_privacy_context',default=PrivacyContext())


@dataclass(frozen=True)
class PrivateMedia:
    content: bytes
    media_type: str
    data_url: bool = False


def private_media(content: bytes, media_type: str, *, data_url: bool = False) -> PrivateMedia:
    """Opaque, unencoded local media. Only privacy_call can materialize it."""
    return PrivateMedia(content,media_type.split(';',1)[0].lower().strip(),data_url)


_DOB_KEYS={'date_of_birth','birth_date','dob','dogum_tarihi'}
_ID_KEYS={'patient_name','full_name','first_name','last_name','surname','national_id','tckn','phone','telephone','email','address','external_ref','protocol_no'}
_FILE_KEYS={'filename','file_name','source_file_name'}


def _sanitize_payload(value: Any, counts: Counter, identifiers: Sequence[str], *, key: str = '', path: tuple[str,...] = ()) -> Any:
    if isinstance(value,PrivateMedia):
        if value.media_type=='application/pdf': data,redactions=_sanitize_pdf(value.content,identifiers)
        else: data,redactions=_sanitize_image(value.content,value.media_type,identifiers)
        counts.update(redactions)
        encoded=base64.b64encode(data).decode('ascii')
        return f'data:{value.media_type};base64,{encoded}' if value.data_url else encoded
    if isinstance(value,bytes): raise PrivacyViolation()
    if isinstance(value,dict):
        # JSON-schema/property names are interface data, not patient records.
        if path == ('text','format','schema'):
            # A static schema must remain byte-for-byte compatible, but is still scanned.
            encoded=json.dumps(value,ensure_ascii=False)
            final_leak_check(encoded,identifiers)
            return value
        result={}
        for field,item in value.items():
            if not isinstance(field,str): raise PrivacyViolation()
            final_leak_check(field,identifiers)
            lowered=field.casefold()
            if lowered in _DOB_KEYS:
                if item is not None and str(item).strip(): counts['DOGUM_TARIHI']+=1
                age=context.get().age
                if age is None and isinstance(item,str):
                    from app.domain.document_dates import calendar_day
                    born=calendar_day(item)
                    if born is not None: age=age_in_years(born)
                if age is not None and 'age' not in value: result['age']=age
                continue
            if lowered in _ID_KEYS and isinstance(item,(str,int)) and str(item).strip():
                category={'phone':'TELEFON','telephone':'TELEFON','email':'EPOSTA','address':'ADRES','national_id':'TCKN','tckn':'TCKN'}.get(lowered,'HASTA_ADI' if 'name' in lowered else 'KAYIT_NO')
                counts[category]+=1; result[field]=f'[{category}]'
            elif lowered in _FILE_KEYS:
                # Filenames can contain identifiers without labels or patient context.
                result[field]='document.pdf' if str(item).lower().endswith('.pdf') else 'document'
                if item: counts['KAYIT_NO']+=1
            else: result[field]=_sanitize_payload(item,counts,identifiers,key=lowered,path=(*path,field))
        return result
    if isinstance(value,(list,tuple)):
        return [_sanitize_payload(item,counts,identifiers,key=key,path=(*path,"[]")) for item in value]
    if isinstance(value,str):
        if key in ('image_url','file_data','data','url'):
            # A raw URL/file-id/base64 string has no local verifiable media source.
            raise PrivacyViolation()
        if value.lstrip().startswith(('{','[')):
            # Heading retries append instructions after the JSON. Decode the
            # prefix too, so escaped line breaks/names cannot evade redaction.
            stripped=value.lstrip()
            try: parsed,end=json.JSONDecoder().raw_decode(stripped)
            except (ValueError,TypeError): parsed,end=None,0
            if isinstance(parsed,(dict,list)):
                prefix=json.dumps(_sanitize_payload(parsed,counts,identifiers,path=('prompt',)),ensure_ascii=False,separators=(',',':'))
                suffix=_sanitize_payload(stripped[end:],counts,identifiers,key='text') if stripped[end:] else ''
                return prefix+suffix
        if value.startswith('data:'): raise PrivacyViolation()
        result=sanitize_text(value,known_identifiers=identifiers)
        counts.update(result.redaction_counts)
        final_leak_check(result.text,identifiers)
        return result.text
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if valid_tckn(str(value)):
            counts['TCKN']+=1
            return '[TCKN]'
        return value
    if value is None or isinstance(value,bool): return value
    # Never pass an unexamined custom SDK/file object to an external service.
    raise PrivacyViolation()


async def privacy_call(operation: Callable[..., Awaitable[Any]], *, provider: str, call_site: str, **payload: Any) -> Any:
    privacy=context.get(); counts=Counter(); blocked=True
    try:
        if privacy.loader is not None:
            privacy=await privacy.loader()
            context.set(privacy)
        sanitized=await asyncio.to_thread(_sanitize_payload,payload,counts,privacy.known_identifiers)
        final_leak_check(json.dumps(sanitized,ensure_ascii=False),privacy.known_identifiers)
        blocked=False
    except PrivacyViolation:
        raise
    except Exception:
        raise PrivacyViolation() from None
    finally:
        event={'timestamp':datetime.now(UTC).isoformat(),'provider':provider,'call_site':call_site,
               'patient_id':privacy.patient_id,'redaction_counts':dict(counts),'blocked':blocked}
        logger.warning('ai_privacy_audit %s',json.dumps(event,ensure_ascii=True,sort_keys=True))
    return await operation(**sanitized)
