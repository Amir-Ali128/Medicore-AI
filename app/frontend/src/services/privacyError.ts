export const PRIVACY_REDACTION_FAILED = 'PRIVACY_REDACTION_FAILED';
export const PRIVACY_FAILURE_MESSAGE = 'Belgedeki kişisel bilgiler güvenli biçimde silinemediği için belge yapay zekâya gönderilmedi. Lütfen kimlik bilgilerinin görünmediği bir sürüm yükleyin.';

export function privacyErrorMessage(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const value = body as { code?: unknown; detail?: unknown };
  const detail = value.detail && typeof value.detail === 'object' ? value.detail as { code?: unknown } : undefined;
  return value.code === PRIVACY_REDACTION_FAILED || detail?.code === PRIVACY_REDACTION_FAILED
    ? PRIVACY_FAILURE_MESSAGE : undefined;
}
