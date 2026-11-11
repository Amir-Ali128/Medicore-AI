"""Immutable, public software assets for the local multilingual ASR engine."""
from pathlib import Path

MODEL_REPOSITORY = 'Systran/faster-whisper-tiny'
MODEL_REVISION = 'd90ca5fe260221311c53c58e660288d3deb8d356'
MODEL_LICENSE = 'MIT'
BUNDLED_MODEL_DIR = Path(__file__).resolve().parents[2] / '.voice_models' / ('whisper-tiny-' + MODEL_REVISION[:12])
READY_FILE = '.verified.json'
# filename: (exact bytes, SHA256). No mutable branch names or remote code loading.
MODEL_FILES = {
    'config.json': (2249, 'a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8'),
    'model.bin': (75538270, 'dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1'),
    'tokenizer.json': (2203239, 'fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab'),
    'vocabulary.txt': (459861, '34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913'),
}


def bundled_model_available(directory: Path | None = None) -> bool:
    """Cheap request-time check; full hashes and multilingual load run at startup."""
    import json
    root = directory if directory is not None else BUNDLED_MODEL_DIR
    try:
        marker = json.loads((root / READY_FILE).read_text())
        return marker == {'revision': MODEL_REVISION, 'language': 'tr'} and all(
            (root / name).is_file() and (root / name).stat().st_size == size
            for name, (size, _digest) in MODEL_FILES.items()
        )
    except (OSError, ValueError, TypeError):
        return False


def effective_voice_model_path(configured: str | None) -> str | None:
    """Explicit operator paths take priority; never fall through a broken override."""
    if configured is not None:
        return configured
    return str(BUNDLED_MODEL_DIR) if bundled_model_available() else None
