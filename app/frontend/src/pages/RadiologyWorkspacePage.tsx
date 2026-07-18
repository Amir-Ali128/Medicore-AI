import { useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import {
  evaluateClaudeAbnormalResults,
  type ClaudeReviewGenerationResult,
} from '../services/claudeReviewClient';
import {
  createManualRadiologyReport,
  uploadRadiologyReportPdf,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950';

type IncludedSources = {
  patient_information?: boolean;
  complaint_and_symptoms?: boolean;
  medical_history?: boolean;
  physical_exam_and_vitals?: boolean;
  laboratory_results?: boolean;
  radiology_and_dexa_reports?: number;
};

function getHypotheses(review: ClaudeReviewGenerationResult | null) {
  if (!review) return [];
  return review.created_hypotheses?.length
    ? review.created_hypotheses
    : review.hypotheses ?? [];
}

function unifiedSummary(
  review: ClaudeReviewGenerationResult | null,
  report: RadiologyReport | null,
) {
  const hypotheses = getHypotheses(review);
  const summaries = hypotheses
    .map((item) => item.summary?.trim())
    .filter((item): item is string => Boolean(item));

  if (summaries.length > 0) {
    return [...new Set(summaries)].slice(0, 4).join('\n\n');
  }

  return report?.impression?.trim() || report?.summary?.trim() || '';
}

function highestSeverity(review: ClaudeReviewGenerationResult | null, report: RadiologyReport | null) {
  const severities = getHypotheses(review).map((item) => item.severity?.toLowerCase() ?? '');
  if (
    severities.some((item) => ['critical', 'emergency', 'urgent', 'high'].includes(item)) ||
    (report?.critical_findings?.length ?? 0) > 0
  ) {
    return 'ACİL';
  }
  if (severities.some((item) => ['moderate', 'medium', 'warning'].includes(item))) {
    return 'DİKKAT';
  }
  return 'RUTİN';
}

function includedSources(review: ClaudeReviewGenerationResult | null): IncludedSources | null {
  const hypothesis = getHypotheses(review)[0];
  const value = hypothesis?.metadata_json?.included_data_sources;
  return value && typeof value === 'object' ? (value as IncludedSources) : null;
}

export default function RadiologyWorkspacePage() {
  const [mode, setMode] = useState<'manual' | 'pdf'>('manual');
  const [reportText, setReportText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<RadiologyReport | null>(null);
  const [review, setReview] = useState<ClaudeReviewGenerationResult | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setStatus('');
    setReview(null);

    try {
      const report =
        mode === 'manual'
          ? await createManualRadiologyReport({
              reportDate: new Date().toISOString().slice(0, 10),
              modality: null,
              bodyPart: null,
              reportText,
            })
          : file
            ? await uploadRadiologyReportPdf(file, {
                reportDate: new Date().toISOString().slice(0, 10),
                modality: null,
                bodyPart: null,
              })
            : (() => {
                throw new Error('Önce bir PDF dosyası seçmelisin.');
              })();

      setResult(report);
      const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');

      if (!analysisRunId) {
        setStatus(
          'Rapor kaydedildi. Birleşik değerlendirme için önce laboratuvar/klinik analiz oluşturulmalıdır.',
        );
        return;
      }

      try {
        const generatedReview = await evaluateClaudeAbnormalResults(analysisRunId, 5);
        setReview(generatedReview);
        setStatus(
          'Rapor; klinik bilgiler, laboratuvar sonuçları ve önceki görüntüleme raporlarıyla birlikte değerlendirildi.',
        );
      } catch {
        setStatus(
          'Rapor kaydedildi ancak birleşik klinik değerlendirme şu anda tamamlanamadı.',
        );
      }
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : 'Radyoloji analizi başarısız.',
      );
    } finally {
      setBusy(false);
    }
  }

  const summary = unifiedSummary(review, result);
  const urgency = highestSeverity(review, result);
  const sources = includedSources(review);
  const urgencyClass =
    urgency === 'ACİL'
      ? 'border-red-300 bg-red-600 text-white'
      : urgency === 'DİKKAT'
        ? 'border-amber-300 bg-amber-100 text-amber-950'
        : 'border-emerald-300 bg-emerald-100 text-emerald-950';

  const sourceLabels = result
    ? [
        'Yeni görüntüleme raporu',
        sources?.patient_information ? 'Hasta bilgileri' : null,
        sources?.complaint_and_symptoms ? 'Şikâyet ve semptomlar' : null,
        sources?.medical_history ? 'Klinik öykü' : null,
        sources?.physical_exam_and_vitals ? 'Muayene ve vital bulgular' : null,
        sources?.laboratory_results ? 'Laboratuvar sonuçları' : null,
        sources?.radiology_and_dexa_reports
          ? `${sources.radiology_and_dexa_reports} görüntüleme/DEXA raporu`
          : null,
      ].filter((item): item is string => Boolean(item))
    : [];

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Raporlama</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">Birleşik klinik değerlendirme</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Görüntüleme raporunu klinik bilgiler, laboratuvar sonuçları ve önceki raporlarla birlikte değerlendirir.
        </p>
      </header>

      <form onSubmit={submit}>
        <SectionCard title="Yeni görüntüleme raporu" description="Metni yapıştır veya PDF yükle.">
          <div className="flex gap-2">
            <button type="button" onClick={() => setMode('manual')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
              Rapor metni
            </button>
            <button type="button" onClick={() => setMode('pdf')} className="rounded-lg border px-4 py-2 text-sm font-semibold">
              PDF yükle
            </button>
          </div>

          {mode === 'manual' ? (
            <textarea
              required
              minLength={10}
              rows={14}
              value={reportText}
              onChange={(event) => setReportText(event.target.value)}
              className={`${INPUT_CLASS} mt-5 resize-y`}
              placeholder="Rapor metnini buraya yapıştır..."
            />
          ) : (
            <input
              required
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className={`${INPUT_CLASS} mt-5`}
            />
          )}

          {status ? (
            <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              {status}
            </p>
          ) : null}
          {error ? (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-60"
          >
            {busy ? 'Tüm veriler değerlendiriliyor…' : 'Kaydet ve tüm verilerle değerlendir'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard title="Birleşik değerlendirme" description={`${result.modality} · ${result.body_part}`}>
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className={`rounded-full border px-4 py-2 text-sm font-extrabold tracking-wide ${urgencyClass}`}>
                Klinik öncelik: {urgency}
              </span>
              <span className="text-xs text-slate-500">Hekim doğrulaması zorunludur.</span>
            </div>

            <section className="rounded-xl border border-blue-200 bg-blue-50 p-5">
              <h2 className="font-semibold text-blue-950">AI klinik özeti</h2>
              {summary ? (
                <p className="mt-3 whitespace-pre-line text-sm leading-7 text-blue-950">{summary}</p>
              ) : (
                <p className="mt-3 text-sm leading-7 text-blue-900">
                  Birleşik klinik özet henüz oluşturulamadı.
                </p>
              )}
              <p className="mt-4 text-xs text-blue-800">
                Bu değerlendirme destek amaçlıdır; tanı veya tedavi kararı değildir.
              </p>
            </section>

            <section>
              <h2 className="text-sm font-semibold text-slate-900">Değerlendirmeye katılan veriler</h2>
              <div className="mt-3 flex flex-wrap gap-2">
                {sourceLabels.map((label) => (
                  <span key={label} className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-700">
                    {label}
                  </span>
                ))}
              </div>
            </section>
          </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
