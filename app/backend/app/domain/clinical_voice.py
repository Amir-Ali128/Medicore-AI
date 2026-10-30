"""Bounded, offline Turkish ASR. Never writes audio, text, or patient records."""
from __future__ import annotations

from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from threading import Lock
from time import monotonic

import numpy as np

SAMPLE_RATE = 16_000
MAX_AUDIO_SECONDS = 15
MAX_AUDIO_BYTES = 2 * 1024 * 1024


class VoiceUnavailable(Exception):
    pass


class VoiceBusy(Exception):
    pass


class InvalidVoiceAudio(Exception):
    pass


def voice_ready(model_path: str | None) -> bool:
    if not model_path or find_spec("faster_whisper") is None:
        return False
    root = Path(model_path)
    return root.is_dir() and all((root / name).is_file() for name in (
        "model.bin", "config.json", "tokenizer.json",
    )) and any((root / name).is_file() for name in ("vocabulary.json", "vocabulary.txt"))


def decode_bounded_audio(data: bytes) -> np.ndarray:
    """Decode at most 15 seconds, including compressed input (no temp files)."""
    import av

    chunks: list[np.ndarray] = []
    samples = 0
    started = monotonic()
    try:
        with av.open(BytesIO(data), mode="r", options={
            # Refuse playlists/remote protocols and externally referenced tracks.
            "protocol_whitelist": "pipe",
            "format_whitelist": "wav,matroska,webm,ogg,mov,mp4,m4a,3gp,3g2,mj2",
        }) as container:
            if not container.streams.audio:
                raise InvalidVoiceAudio()
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                if monotonic() - started > 5 or not frame.sample_rate or frame.samples / frame.sample_rate > MAX_AUDIO_SECONDS:
                    raise InvalidVoiceAudio()
                for output in resampler.resample(frame):
                    samples += output.samples
                    if samples > SAMPLE_RATE * MAX_AUDIO_SECONDS:
                        raise InvalidVoiceAudio()
                    chunks.append(output.to_ndarray().reshape(-1))
            for output in resampler.resample(None):
                samples += output.samples
                if samples > SAMPLE_RATE * MAX_AUDIO_SECONDS:
                    raise InvalidVoiceAudio()
                chunks.append(output.to_ndarray().reshape(-1))
    except InvalidVoiceAudio:
        raise
    except Exception:
        raise InvalidVoiceAudio() from None
    if not chunks:
        raise InvalidVoiceAudio()
    audio = np.concatenate(chunks).astype(np.float32, copy=False)
    if not np.isfinite(audio).all():
        raise InvalidVoiceAudio()
    return audio


class OfflineTurkishRecognizer:
    def __init__(self):
        self._lock = Lock()
        self._model = None
        self._model_path: str | None = None

    def transcribe(self, data: bytes, model_path: str | None) -> dict:
        if not voice_ready(model_path):
            raise VoiceUnavailable()
        if not self._lock.acquire(blocking=False):
            raise VoiceBusy()
        try:
            samples = decode_bounded_audio(data)
            duration = len(samples) / SAMPLE_RATE
            # Suppress the common silence hallucination case before inference.
            if duration < 0.25 or float(np.sqrt(np.mean(samples ** 2))) < 0.001:
                return {"text": "", "duration_seconds": round(duration, 3), "language": "tr"}
            if self._model is None or self._model_path != model_path:
                import onnxruntime

                onnxruntime.disable_telemetry_events()
                from faster_whisper import WhisperModel

                # A real local directory plus local_files_only prevents the
                # library's model-name/network fallback, even on a cache miss.
                self._model = WhisperModel(str(Path(model_path).resolve()), device="cpu", compute_type="int8",
                                           cpu_threads=2, num_workers=1, local_files_only=True)
                if "tr" not in self._model.supported_languages:
                    self._model = None
                    raise VoiceUnavailable()
                self._model_path = model_path
            segments, _info = self._model.transcribe(
                samples, language="tr", task="transcribe", beam_size=3,
                temperature=0, condition_on_previous_text=False, vad_filter=True,
            )
            decoded = list(segments)
            text = " ".join(segment.text.strip() for segment in decoded if segment.text.strip())
            if len(text) > 12000:
                raise InvalidVoiceAudio()
            review = any(segment.avg_logprob < -0.8 or segment.no_speech_prob > 0.6 for segment in decoded)
            return {"text": text, "duration_seconds": round(duration, 3), "language": "tr", "needs_review": review}
        finally:
            self._lock.release()


recognizer = OfflineTurkishRecognizer()
