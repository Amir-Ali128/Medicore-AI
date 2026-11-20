"""Local-only AI: clinical reports from a self-hosted model, external providers blocked."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from openai import AsyncOpenAI

from app.domain import simple_case_ai
from app.infrastructure import ai_privacy_client, local_llm
from app.infrastructure.ai_privacy_client import privacy_call
from app.schemas.simple_case import ClinicalContext, LabResultInput, SimpleCaseRequest

HEADINGS = ("KLİNİK ÖZET", "ÖNE ÇIKAN LABORATUVAR BULGULARI", "TETKİK / RAPOR BULGULARI",
            "ENTEGRE KLİNİK DEĞERLENDİRME", "OLASI KLİNİK DURUMLAR / AYIRICI TANI",
            "ÖNERİLEN İLERİ TETKİK / İZLEM", "SONUÇ / KANAAT", "HEKİM NOTU")
FULL_REPORT = "\n\n".join(f"{heading}\nKronik böbrek hastalığı ile uyumlu olabilir; hekim değerlendirmesi gerekir."
                          for heading in HEADINGS)


def _settings(**overrides):
    base = dict(ai_local_only=True, local_llm_base_url="http://127.0.0.1:1234/v1", local_llm_model="qwen2.5-14b-instruct",
                local_llm_api_key=None, local_llm_timeout_seconds=30.0, local_llm_max_tokens=6000,
                local_llm_trusted_hosts="", anthropic_api_key="sk-should-not-be-used", claude_hypothesis_model="claude-x",
                claude_extraction_model=None, claude_vision_model=None, report_consistency_enabled=False,
                lab_consistency_rules_enabled=False, consistency_section_enabled=False)
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def settings(monkeypatch):
    current = _settings()
    for module in (local_llm, simple_case_ai):
        monkeypatch.setattr(module, "get_settings", lambda: current)
    return current


def _fake_local_server(reply=FULL_REPORT, finish="stop"):
    app = FastAPI()
    app.state.requests = []

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        app.state.requests.append(body)
        return {"id": "x", "object": "chat.completion", "created": 0, "model": body["model"],
                "choices": [{"index": 0, "finish_reason": finish,
                             "message": {"role": "assistant", "content": reply}}]}
    return app


def _use_server(monkeypatch, app):
    def client():
        return AsyncOpenAI(base_url=local_llm.validated_base_url(), api_key="local", max_retries=0,
                           http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app)))
    monkeypatch.setattr(local_llm, "local_client", client)


def _case():
    return SimpleCaseRequest(
        clinical=ClinicalContext(age=65, sex="male", complaints=["bacaklarda şişlik", "Dr. Ahmet Yılmaz yönlendirdi"]),
        labs=[LabResultInput(test_name="Kreatinin", value="3,9", unit="mg/dL", source_reference="0,67 - 1,17")],
    )


# ---------------------------------------------------------------- endpoint policy
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "192.168.1.20", "172.16.3.4", "::1",
                                  "ollama", "llm-server", "gpu.internal", "box.local", "host.docker.internal"])
def test_private_hosts_are_accepted(host):
    assert local_llm.is_private_host(host)


@pytest.mark.parametrize("host", ["api.openai.com", "api.anthropic.com", "8.8.8.8", "my-llm.onrender.com", ""])
def test_public_hosts_are_refused(host):
    assert not local_llm.is_private_host(host)


def test_public_base_url_is_refused_unless_explicitly_trusted(settings):
    settings.local_llm_base_url = "https://gpu.example.com/v1"
    with pytest.raises(local_llm.LocalLLMNotConfigured, match="yerel/özel"):
        local_llm.validated_base_url()
    settings.local_llm_trusted_hosts = "gpu.example.com"
    assert local_llm.validated_base_url() == "https://gpu.example.com/v1"


def test_missing_local_configuration_is_explained(settings):
    settings.local_llm_model = None
    with pytest.raises(local_llm.LocalLLMNotConfigured, match="LOCAL_LLM_MODEL"):
        local_llm.validated_base_url()


# ---------------------------------------------------------------- single enforcement point
@pytest.mark.parametrize("provider", ["Anthropic", "OpenAI", "Gemini"])
def test_local_only_blocks_every_external_provider(settings, provider):
    called = []

    async def external(**payload):
        called.append(payload)

    with pytest.raises(local_llm.ExternalAIBlocked, match="dışarı gönderilmedi"):
        asyncio.run(privacy_call(external, provider=provider, call_site="test", messages=[{"role": "user", "content": "x"}]))
    assert called == []


def test_local_provider_passes_and_is_still_sanitized(settings):
    seen = []

    async def local(**payload):
        seen.append(payload)
        return "ok"

    assert asyncio.run(privacy_call(local, provider=local_llm.LOCAL_PROVIDER, call_site="test",
                                    messages=[{"role": "user", "content": "Uzm. Dr. Ayşe Kaya, TC 12345678950"}])) == "ok"
    sent = json.dumps(seen[0], ensure_ascii=False)
    assert "Ayşe" not in sent and "12345678950" not in sent and "[HEKIM]" in sent


def test_external_providers_work_again_when_local_only_is_off(settings):
    settings.ai_local_only = False

    async def external(**payload):
        return "sent"

    assert asyncio.run(privacy_call(external, provider="Anthropic", call_site="test", messages=[])) == "sent"


# ---------------------------------------------------------------- clinical report via the local model
def test_clinical_report_is_written_by_the_local_model(settings, monkeypatch):
    server = _fake_local_server()
    _use_server(monkeypatch, server)

    def no_anthropic(*args, **kwargs):
        raise AssertionError("Anthropic client must not be created in local mode")

    monkeypatch.setattr(simple_case_ai, "AsyncAnthropic", no_anthropic)
    result = asyncio.run(simple_case_ai.interpret_simple_case(_case()))
    assert result.model == "qwen2.5-14b-instruct"
    assert "KLİNİK ÖZET" in result.report_text and "olabilir" in result.report_text
    request = server.state.requests[0]
    assert request["model"] == "qwen2.5-14b-instruct" and request["messages"][0]["role"] == "system"
    sent = json.dumps(request, ensure_ascii=False)
    assert "Ahmet Yılmaz" not in sent and "[HEKIM]" in sent  # privacy gateway still applies locally
    assert "Kreatinin" in sent


def test_truncated_local_answer_is_retried_and_never_saved_half(settings, monkeypatch):
    server = _fake_local_server(reply="KLİNİK ÖZET\nyarım", finish="length")
    _use_server(monkeypatch, server)
    with pytest.raises(RuntimeError, match="çıktı sınırında kesildi"):
        asyncio.run(simple_case_ai.interpret_simple_case(_case()))
    assert len(server.state.requests) == 2


def test_unreachable_local_server_gives_a_clear_message(settings, monkeypatch):
    settings.local_llm_base_url = "http://127.0.0.1:9/v1"  # nothing listens here

    def client():
        return AsyncOpenAI(base_url=local_llm.validated_base_url(), api_key="local", max_retries=0, timeout=2)

    monkeypatch.setattr(local_llm, "local_client", client)
    with pytest.raises(RuntimeError, match="Yerel AI sunucusuna ulaşılamadı"):
        asyncio.run(simple_case_ai.interpret_simple_case(_case()))


def test_local_only_without_a_local_model_fails_closed(settings, monkeypatch):
    settings.local_llm_base_url = None
    with pytest.raises(RuntimeError, match="Yerel AI modeli yapılandırılmamış"):
        asyncio.run(simple_case_ai.interpret_simple_case(_case()))
