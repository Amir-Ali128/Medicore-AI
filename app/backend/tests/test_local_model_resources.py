"""Heavy local engines never infer concurrently or keep both caches resident."""
from threading import Event, Thread
from unittest.mock import Mock

import pytest

from app.infrastructure import local_model_resources as resources
from app.domain import clinical_voice as voice


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setattr(resources, '_releasers', {})
    monkeypatch.setattr(resources, '_active', None)


def test_switch_evicts_other_engine_only(isolated):
    ocr, asr = Mock(), Mock()
    resources.register_model('ocr', ocr)
    resources.register_model('voice', asr)
    with resources.model_lock:
        resources.activate_model('voice')
        resources.activate_model('voice')
        ocr.assert_called_once_with()
        asr.assert_not_called()
        resources.activate_model('ocr')
        asr.assert_called_once_with()


def test_busy_ocr_rejects_voice_before_decode(isolated, monkeypatch):
    held, finish = Event(), Event()
    def work():
        with resources.model_lock:
            held.set()
            finish.wait(5)
    worker = Thread(target=work)
    worker.start()
    try:
        assert held.wait(2)
        monkeypatch.setattr(voice, 'voice_ready', lambda _: True)
        decode = Mock(side_effect=AssertionError('must not decode while busy'))
        monkeypatch.setattr(voice, 'decode_bounded_audio', decode)
        with pytest.raises(voice.VoiceBusy):
            voice.OfflineTurkishRecognizer().transcribe(b'audio', '/local/model')
        decode.assert_not_called()
    finally:
        finish.set()
        worker.join(2)
    assert not worker.is_alive()


def test_voice_model_released_before_ocr_activation(isolated):
    recognizer = voice.OfflineTurkishRecognizer()
    recognizer._model = object()
    recognizer._model_path = '/local/model'
    resources.register_model('voice', recognizer.release)
    with resources.model_lock:
        resources.activate_model('ocr')
    assert recognizer._model is None and recognizer._model_path is None


def test_failed_eviction_does_not_mark_new_engine_active(isolated):
    resources.register_model('ocr', Mock(side_effect=RuntimeError('release failed')))
    with resources.model_lock, pytest.raises(RuntimeError):
        resources.activate_model('voice')
    assert resources._active is None
