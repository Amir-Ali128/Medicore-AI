"""Prepare pinned public weights before serving requests. No audio/text input.

Network access exists only in this startup/build helper. The recognizer remains
local_files_only=True. Hashes are checked before loading weights; failed downloads
never create a readiness marker. A process/file lock protects shared deployments.
"""
from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
from pathlib import Path
from time import monotonic
from urllib.request import urlopen

from app.domain.voice_model_assets import (
    BUNDLED_MODEL_DIR, MODEL_FILES, MODEL_REPOSITORY, MODEL_REVISION, READY_FILE,
)

logger = logging.getLogger(__name__)
PREPARATION_TIMEOUT_SECONDS = 180.0
CHUNK_BYTES = 1024 * 1024


class VoicePreparationError(Exception):
    def __init__(self):
        super().__init__('Yerel Türkçe ses modeli sunucu hazırlığında doğrulanamadı.')


def _valid_file(path: Path, size: int, digest: str) -> bool:
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size != size:
            return False
        result = hashlib.sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(CHUNK_BYTES): result.update(chunk)
        return result.hexdigest() == digest
    except OSError:
        return False


def _download(name: str, destination: Path, size: int, digest: str, *, deadline: float) -> None:
    """A fixed HTTPS software URL, bounded bytes/time, no user-derived parameters."""
    url = f'https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{name}'
    temporary = destination.with_name(name + '.part')
    try:
        checksum = hashlib.sha256()
        total = 0
        with urlopen(url, timeout=30) as response, temporary.open('wb') as output:
            if not response.geturl().startswith('https://'):
                raise VoicePreparationError()
            while chunk := response.read(CHUNK_BYTES):
                total += len(chunk)
                if total > size or monotonic() > deadline: raise VoicePreparationError()
                checksum.update(chunk)
                output.write(chunk)
        if total != size or checksum.hexdigest() != digest: raise VoicePreparationError()
        temporary.replace(destination)
    except Exception:
        raise VoicePreparationError() from None
    finally:
        temporary.unlink(missing_ok=True)


def prepare_bundled_voice_model(directory: Path | None = None) -> str:
    """Only call from process preparation/build, never from a transcription route."""
    from app.domain.clinical_voice import recognizer
    root = directory if directory is not None else BUNDLED_MODEL_DIR
    try:
        root.mkdir(parents=True, exist_ok=True)
        if root.is_symlink(): raise VoicePreparationError()
        with (root / '.prepare.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            deadline = monotonic() + PREPARATION_TIMEOUT_SECONDS
            marker = root / READY_FILE
            marker.unlink(missing_ok=True)
            for name, (size, digest) in MODEL_FILES.items():
                target = root / name
                if not _valid_file(target, size, digest):
                    _download(name, target, size, digest, deadline=deadline)
                if not _valid_file(target, size, digest): raise VoicePreparationError()
            # Multilingual support and local CPU/int8 loading must succeed before ready.
            recognizer.prepare(str(root))
            temporary = root / (READY_FILE + '.part')
            temporary.write_text(json.dumps({'revision': MODEL_REVISION, 'language': 'tr'}))
            temporary.replace(marker)
        logger.info('Offline Turkish voice assets verified; local CPU/int8 engine ready.')
        return str(root)
    except Exception:
        raise VoicePreparationError() from None


async def prepare_offline_voice() -> str:
    from app.core.config import get_settings
    from app.domain.clinical_voice import recognizer
    configured = get_settings().clinical_voice_model_path
    if configured is not None:
        await asyncio.to_thread(recognizer.prepare, configured)
        return 'operator-local-model'
    await asyncio.to_thread(prepare_bundled_voice_model)
    return 'bundled-multilingual-tiny'


if __name__ == '__main__':
    prepare_bundled_voice_model()
