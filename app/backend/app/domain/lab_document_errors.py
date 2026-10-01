"""Safe diagnostics for laboratory readers, without provider bodies or secrets."""
from __future__ import annotations

from typing import Any


def reader_failure(reader: str, exc: Exception) -> dict[str, Any]:
    chain = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    status = next((getattr(item, 'status_code', None) for item in reversed(chain)
                   if isinstance(getattr(item, 'status_code', None), int)), None)
    names = {type(item).__name__ for item in chain}
    # Match known configuration messages, never echo arbitrary exception text.
    missing_config = any(str(item).startswith((
        'OPENAI_API_KEY yapılandırılmamış.', 'OPENAI_LAB_MODEL yapılandırılmamış.',
        'ANTHROPIC_API_KEY is not configured.', 'CLAUDE_EXTRACTION_MODEL is not configured.',
    )) for item in chain)
    if missing_config:
        code, message = 'not_configured', 'belge okuma yapılandırması eksik; sunucu ayarları kontrol edilmeli.'
    elif status in {401, 403}:
        code, message = 'access_denied', 'belge okuma erişimi reddedildi; sunucudaki anahtar ve erişim izinleri kontrol edilmeli.'
    elif status == 404:
        code, message = 'model_unavailable', 'yapılandırılmış belge okuma modeline erişilemiyor; model erişimi kontrol edilmeli.'
    elif status == 429:
        code, message = 'rate_or_quota_limit', 'belge okuma kullanım sınırına ulaşıldı; kota veya istek sınırı kontrol edilmeli.'
    elif any('Timeout' in name for name in names):
        code, message = 'timeout', 'belge okuma süre sınırını aştı; lütfen yeniden deneyin.'
    elif names & {'DependencyBusyError', 'DependencyCircuitOpenError', 'CircuitOpenError'}:
        code, message = 'temporarily_unavailable', 'belge okuyucu geçici olarak meşgul; lütfen yeniden deneyin.'
    else:
        code, message = 'request_failed', 'belge okuma isteği tamamlanamadı; lütfen yeniden deneyin.'
    return {'reader': reader, 'code': code, 'message': f'{reader}: {message}', 'status': status}


class LabDocumentReadError(ValueError):
    def __init__(self, page_reports: list[dict[str, Any]]) -> None:
        self.page_reports = page_reports
        failures = []
        seen = set()
        for page in page_reports:
            for error in page.get('extraction_errors', []):
                identity = (error['reader'], error['code'])
                if identity not in seen:
                    failures.append(f"Sayfa {page['page']} — {error['message']}")
                    seen.add(identity)
        message = 'Belgeden laboratuvar sonucu okunamadı. '
        message += ' '.join(failures[:4]) if failures else (
            'Tablonun tamamının göründüğü, yazıları net bir PDF veya fotoğraf yükleyin. '
            'Fotoğraf yan dönmüşse dönüş seçeneğini kullanın.'
        )
        super().__init__(message)
