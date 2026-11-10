"""Authenticated, transient audio-to-text; no patient persistence dependency."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.routes.auth import get_current_active_user
from app.core.config import get_settings
from app.domain.clinical_voice import (
    MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, InvalidVoiceAudio, VoiceBusy,
    VoiceUnavailable, recognizer, voice_ready,
)
from app.infrastructure.database.models.user import User
from app.domain.voice_model_assets import effective_voice_model_path

router = APIRouter(prefix="/clinical-voice", tags=["clinical-voice"])
_User = Annotated[User, Depends(get_current_active_user)]


@router.get("/capabilities")
async def capabilities(_user: _User) -> dict:
    return {"ready": voice_ready(effective_voice_model_path(get_settings().clinical_voice_model_path)),
            "language": "tr", "processing": "medicore-server-offline",
            "max_audio_seconds": MAX_AUDIO_SECONDS}


@router.post("/transcribe")
async def transcribe(request: Request, response: Response, _user: _User) -> dict:
    response.headers["Cache-Control"] = "no-store"
    media_type = request.headers.get("content-type", "").split(";")[0].lower()
    if media_type not in {"audio/webm", "audio/ogg", "audio/mp4", "audio/wav", "audio/x-wav"}:
        raise HTTPException(415, "Desteklenmeyen ses biçimi.")
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Ses parçası çok büyük; daha kısa bir kayıt kullanın.")
    path = effective_voice_model_path(get_settings().clinical_voice_model_path)
    if not voice_ready(path):
        raise HTTPException(503, "Yerel Türkçe ses modeli henüz hazırlanmadı. Metni elle girebilirsiniz.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Ses parçası çok büyük; daha kısa bir kayıt kullanın.")
        data.extend(chunk)
    if not data:
        raise HTTPException(422, "Boş ses kaydı.")
    try:
        return await run_in_threadpool(recognizer.transcribe, bytes(data), path)
    except VoiceUnavailable:
        raise HTTPException(503, "Yerel Türkçe ses modeli kullanılamıyor.") from None
    except VoiceBusy:
        raise HTTPException(429, "Ses motoru meşgul. Kısa bir süre sonra tekrar deneyin.") from None
    except InvalidVoiceAudio:
        raise HTTPException(422, "Ses çözümlenemedi veya 15 saniyelik parça sınırı aşıldı.") from None
    except Exception:
        # Never include decoder/model errors, audio or transcripts in logs/responses.
        raise HTTPException(503, "Ses metne dönüştürülemedi. Metni elle düzeltebilir veya tekrar deneyebilirsiniz.") from None
