"""Offline readiness check: can Medicore run on this machine with no internet?

Run inside the backend container:
    docker compose -f docker-compose.offline.yml --env-file offline.env exec backend python scripts/offline_check.py

Exit code 0 when every required item passes. No patient data is read or sent.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402

RESULTS: list[tuple[bool, bool, str]] = []  # (ok, required, message)


def report(ok: bool, message: str, *, required: bool = True) -> None:
    RESULTS.append((ok, required, message))


def check_local_only() -> None:
    settings = get_settings()
    report(bool(settings.ai_local_only), "AI_LOCAL_ONLY açık (dış AI servisleri kapalı)")
    external = [name for name in ("anthropic_api_key", "openai_api_key", "gemini_api_key")
                if getattr(settings, name, None)]
    report(not external, "Dış AI anahtarı tanımlı değil" + (f" (tanımlı: {', '.join(external)})" if external else ""),
           required=False)


async def check_local_llm() -> None:
    from app.infrastructure.local_llm import LocalLLMNotConfigured, validated_base_url

    settings = get_settings()
    try:
        base = validated_base_url()
    except LocalLLMNotConfigured as exc:
        report(False, f"Yerel model adresi: {exc}")
        return
    report(True, f"Yerel model adresi yerel/özel: {base}")
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            response = await client.get(f"{base}/models")
        names = [item.get("id") for item in response.json().get("data", [])] if response.status_code == 200 else []
    except Exception:
        report(False, "Yerel model sunucusuna ulaşılamadı (LM Studio/Ollama sunucusu açık mı?)")
        return
    report(settings.local_llm_model in names,
           f"Model yüklü: {settings.local_llm_model}" if settings.local_llm_model in names
           else f"Model bulunamadı: {settings.local_llm_model} (sunucudakiler: {', '.join(map(str, names)) or '-'})")


async def check_database() -> None:
    from sqlalchemy import text

    from app.infrastructure.database.session import AsyncSessionFactory

    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        report(True, "Veritabanı bağlantısı")
    except Exception:
        report(False, "Veritabanına bağlanılamadı")


def check_voice() -> None:
    from app.domain.voice_model_assets import BUNDLED_MODEL_DIR, MODEL_FILES, READY_FILE
    from app.infrastructure.voice_model_provisioning import _valid_file

    configured = get_settings().clinical_voice_model_path
    if configured:
        report(Path(configured).is_dir(), f"Ses modeli (operatör yolu): {configured}", required=False)
        return
    ready = (BUNDLED_MODEL_DIR / READY_FILE).is_file() and all(
        _valid_file(BUNDLED_MODEL_DIR / name, size, digest) for name, (size, digest) in MODEL_FILES.items()
    )
    report(ready, "Türkçe ses modeli pakette ve doğrulanmış", required=False)


def check_ocr() -> None:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        report(True, "Yerel OCR (taranmış belge okuma) kurulu", required=False)
    except Exception:
        report(False, "Yerel OCR kurulu değil (taranmış belgeler okunamaz)", required=False)


async def check_hbys() -> None:
    base = get_settings().hbys_base_url
    if not base:
        report(True, "HBYS bağlantısı tanımlı değil (isteğe bağlı)", required=False)
        return
    try:
        async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
            ok = (await client.get(f"{base.rstrip('/')}/health")).status_code == 200
    except Exception:
        ok = False
    report(ok, f"Sanal HBYS erişilebilir: {base}", required=False)


async def main() -> int:
    check_local_only()
    await check_local_llm()
    await check_database()
    check_voice()
    check_ocr()
    await check_hbys()
    print("\nMedicore internetsiz çalışma kontrolü\n" + "-" * 40)
    for ok, required, message in RESULTS:
        mark = "✅" if ok else ("❌" if required else "⚠️ ")
        print(f"{mark} {message}")
    failed = [message for ok, required, message in RESULTS if required and not ok]
    print("-" * 40)
    print("HAZIR: internet olmadan çalışabilir." if not failed else f"HAZIR DEĞİL: {len(failed)} zorunlu madde eksik.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
