import type { RadiologyReport } from './radiologyClient';

function clean(value: unknown, max = 320) {
  if (typeof value !== 'string') return '';
  const text = value.replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function formatDate(value: string | null | undefined) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return new Intl.DateTimeFormat('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(parsed);
}

/** Return the newest explicit, de-identified radiologist comparison statement. */
export function buildRadiologyComparisonSummary(reports: RadiologyReport[]) {
  const candidates = reports
    .map((report) => {
      const comparison = clean(report.metadata_json?.comparison_text, 280);
      if (!comparison) return null;
      const date = formatDate(report.report_date);
      const timestamp = Date.parse(report.report_date || report.updated_at || report.created_at || '') || 0;
      return {
        text: `${date ? `${date} · ` : ''}${comparison}`,
        timestamp,
      };
    })
    .filter((item): item is { text: string; timestamp: number } => Boolean(item));

  candidates.sort((a, b) => b.timestamp - a.timestamp);
  return candidates[0]?.text ?? '';
}
