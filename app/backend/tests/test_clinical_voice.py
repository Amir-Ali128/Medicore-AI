"""ASR privacy/limits/authentication without production DB or remote providers."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import wave

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import auth, clinical_voice as route
from app.domain import clinical_voice as voice


def wav(seconds=1, *, rate=16000, amplitude=0.1):
    samples = np.sin(np.arange(int(seconds * rate)) * 2 * np.pi * 220 / rate) * amplitude
    output = BytesIO()
    with wave.open(output, "wb") as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(rate)
        file.writeframes((samples * 32767).astype(np.int16).tobytes())
    return output.getvalue()


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    user = SimpleNamespace(id="doctor-test", is_active=True)
    app.dependency_overrides[auth.get_current_active_user] = lambda: user
    monkeypatch.setattr(route, "get_settings", lambda: SimpleNamespace(clinical_voice_model_path="/configured/model"))
    monkeypatch.setattr(route, "voice_ready", lambda path: True)
    transcribe = Mock(return_value={"text": "Hasta 65 yaşında. Nabız 108.", "language": "tr", "duration_seconds": 1, "needs_review": False})
    monkeypatch.setattr(route, "recognizer", SimpleNamespace(transcribe=transcribe))
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, app=app, transcribe=transcribe)


def test_voice_endpoints_require_authentication(api):
    api.app.dependency_overrides.clear()
    assert api.client.get("/clinical-voice/capabilities").status_code == 401
    assert api.client.post("/clinical-voice/transcribe", content=b"private audio", headers={"Content-Type": "audio/webm"}).status_code == 401
    api.transcribe.assert_not_called()


def test_caps_identifies_offline_turkish_engine(api):
    response = api.client.get("/clinical-voice/capabilities")
    assert response.json() == {"ready": True, "language": "tr", "processing": "medicore-server-offline", "max_audio_seconds": 15}


def test_missing_assets_are_unavailable_without_any_recognition_or_persistence(api, monkeypatch):
    monkeypatch.setattr(route, "voice_ready", lambda path: False)
    assert api.client.get("/clinical-voice/capabilities").json()["ready"] is False
    response = api.client.post("/clinical-voice/transcribe", content=wav(), headers={"Content-Type": "audio/wav"})
    assert response.status_code == 503
    api.transcribe.assert_not_called()


def test_transcription_returns_only_text_and_never_creates_a_patient(api, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = wav()
    response = api.client.post("/clinical-voice/transcribe", content=data, headers={"Content-Type": "audio/wav"})
    assert response.status_code == 200
    assert response.json()["text"] == "Hasta 65 yaşında. Nabız 108."
    assert response.headers["cache-control"] == "no-store"
    api.transcribe.assert_called_once_with(data, "/configured/model")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("media_type", ["text/plain", "application/json", "video/mp4", ""])
def test_non_audio_content_is_rejected(api, media_type):
    assert api.client.post("/clinical-voice/transcribe", content=b"data", headers={"Content-Type": media_type}).status_code == 415
    api.transcribe.assert_not_called()


def test_size_limit_and_empty_bodies_do_not_reach_recognition(api):
    assert api.client.post("/clinical-voice/transcribe", content=b"x" * (voice.MAX_AUDIO_BYTES + 1), headers={"Content-Type": "audio/webm"}).status_code == 413
    assert api.client.post("/clinical-voice/transcribe", content=b"", headers={"Content-Type": "audio/webm"}).status_code == 422
    api.transcribe.assert_not_called()


@pytest.mark.parametrize("failure,status", [(voice.VoiceBusy(), 429), (voice.VoiceUnavailable(), 503), (voice.InvalidVoiceAudio(), 422), (RuntimeError("secret patient transcript"), 503)])
def test_engine_errors_are_bounded_and_do_not_disclose_private_content(api, failure, status, caplog):
    api.transcribe.side_effect = failure
    response = api.client.post("/clinical-voice/transcribe", content=b"audio", headers={"Content-Type": "audio/webm"})
    assert response.status_code == status
    assert "secret patient transcript" not in response.text + caplog.text


def test_readiness_requires_real_local_files_and_an_installed_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "find_spec", lambda module: object())
    assert not voice.voice_ready(None)
    assert not voice.voice_ready(str(tmp_path))
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt"):
        (tmp_path / name).write_bytes(b"local test asset")
    assert voice.voice_ready(str(tmp_path))
    monkeypatch.setattr(voice, "find_spec", lambda module: None)
    assert not voice.voice_ready(str(tmp_path))


def test_real_decoder_limits_compressed_duration_and_rejects_invalid_audio():
    audio = voice.decode_bounded_audio(wav(0.5, rate=22050))
    assert audio.dtype == np.float32
    assert 7900 <= len(audio) <= 8100
    with pytest.raises(voice.InvalidVoiceAudio):
        voice.decode_bounded_audio(wav(16))
    with pytest.raises(voice.InvalidVoiceAudio):
        voice.decode_bounded_audio(b"not an audio file")


def test_audio_cannot_reference_remote_playlists_or_files(monkeypatch):
    import av
    actual_open = av.open
    calls = []
    def guarded_open(*args, **kwargs):
        calls.append(kwargs["options"])
        return actual_open(*args, **kwargs)
    monkeypatch.setattr(av, "open", guarded_open)
    playlist = b"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nhttps://example.invalid/private-audio.ts\n#EXT-X-ENDLIST\n"
    with pytest.raises(voice.InvalidVoiceAudio):
        voice.decode_bounded_audio(playlist)
    assert calls[0]["protocol_whitelist"] == "pipe"
    assert "hls" not in calls[0]["format_whitelist"]


def test_silence_never_reaches_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "voice_ready", lambda path: True)
    recognizer = voice.OfflineTurkishRecognizer()
    assert recognizer.transcribe(wav(amplitude=0), str(tmp_path))["text"] == ""
    assert recognizer._model is None


def test_offline_inference_uses_fixed_turkish_local_files_only_and_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "voice_ready", lambda path: True)
    segment = SimpleNamespace(text="Nabız 108", avg_logprob=-0.9, no_speech_prob=0.05)
    model = SimpleNamespace(transcribe=Mock(return_value=([segment], None)), supported_languages=["tr", "en"])
    constructor = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=constructor))
    telemetry = Mock()
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(disable_telemetry_events=telemetry))
    import socket
    monkeypatch.setattr(socket.socket, "connect", Mock(side_effect=AssertionError("No outbound networking allowed")))
    recognizer = voice.OfflineTurkishRecognizer()
    result = recognizer.transcribe(wav(), str(tmp_path))
    assert result["text"] == "Nabız 108"
    assert result["needs_review"] is True
    constructor.assert_called_once_with(str(tmp_path.resolve()), device="cpu", compute_type="int8", cpu_threads=2, num_workers=1, local_files_only=True)
    telemetry.assert_called_once()
    assert model.transcribe.call_args.kwargs["language"] == "tr"
    recognizer.transcribe(wav(), str(tmp_path))
    assert constructor.call_count == 1


def test_english_only_models_cannot_silently_override_the_turkish_language(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "voice_ready", lambda path: True)
    model = SimpleNamespace(transcribe=Mock(), supported_languages=["en"])
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Mock(return_value=model)))
    monkeypatch.setitem(sys.modules, "onnxruntime", SimpleNamespace(disable_telemetry_events=Mock()))
    with pytest.raises(voice.VoiceUnavailable):
        voice.OfflineTurkishRecognizer().transcribe(wav(), str(tmp_path))
    model.transcribe.assert_not_called()


def test_busy_lock_rejects_extra_work_without_decoding(monkeypatch):
    monkeypatch.setattr(voice, "voice_ready", lambda path: True)
    recognizer = voice.OfflineTurkishRecognizer()
    recognizer._lock.acquire()
    try:
        with pytest.raises(voice.VoiceBusy):
            recognizer.transcribe(b"invalid", "/model")
    finally:
        recognizer._lock.release()


def test_decoder_failure_releases_capacity_for_the_next_request(monkeypatch):
    monkeypatch.setattr(voice, "voice_ready", lambda path: True)
    recognizer = voice.OfflineTurkishRecognizer()
    with pytest.raises(voice.InvalidVoiceAudio):
        recognizer.transcribe(b"invalid", "/model")
    assert recognizer.transcribe(wav(amplitude=0), "/model")["text"] == ""
