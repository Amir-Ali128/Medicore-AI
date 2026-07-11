import { useEffect, useMemo, useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import {
  createManualRadiologyReport,
  listPatientRadiologyReports,
  uploadRadiologyReportPdf,
  type RadiologyFinding,
  type RadiologyReport,
} from '../services/radiologyClient';

type InputMode = 'manual' | 'pdf';

const MODALITIES = [
  ['UNKNOWN', 'Otomatik belirle'],
  ['XRAY', 'Röntgen / Grafi'],
  ['ULTRASOUND', 'Ultrason / USG'],
  ['CT', 'BT / CT'],
  ['MRI', 'MR / MRI'],
  ['PET_CT', 'PET-BT'],
] as const;

const BODY_PARTS = [
  ['OTHER', 'Otomatik belirle'],
  ['BRAIN', 'Beyin / Kraniyal'],
  ['CHEST', 'Toraks / Akciğer'],
  ['ABDOMEN', 'Abdomen'],
  ['PELVIS', 'Pelvis'],
  ['SPINE', 'Omurga'],
  ['NECK', 'Boyun'],
  ['BREAST', 'Meme'],
  ['CARDIAC', 'Kardiyak'],
  ['MUSCULOSKELETAL', 'Kas-iskelet'],
  ['WHOLE_BODY', 'Tüm vücut'],
] as const;

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400';

function todayValue() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value: string | null) {
  if (!value) return 'Tarih belirtilmedi';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(
    new Date(`${value}T12:00:00`),
  );
}

function findingClass(finding: RadiologyFinding) {
  if (finding.is_critical || finding.classification === 'critical') {
    return 'border-red-200 bg-red-50 text-red-950';
  }
  if (finding.classification === 'abnormal') {
    return 'border-amber-200 bg-amber-50 text-amber-950';
  }
  return 'border-slate-200 bg-slate-50 text-slate-700';
}

function ReportResult({ report }: { report: RadiologyReport }) {
  const counts = useMemo(
    () => ({
      critical: report.findings.filter((item) => item.is_critical).length,
      abnormal: report.findings.filter(
        (item) => !item.is_critical && item.classification === 'abnormal',
      ).length,
    }),
    [report],
  );

  return (
    <div className="space-y-5">
      {report.critical_findings.length > 0 ? (
        <div className="rounded-xl border border-red-300 bg-red-50 p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-red-700">
            Kritik ifade uyarısı · Hekim doğrulaması gerekli
          </p>
          <ul className="mt-3 space-y-2 text-sm font-semibold text-red-950">
            {report.critical_findings.map((finding) => (
              <li key={finding}>• {finding}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          Parser kritik terim uyarısı üretmedi. Bu, raporun klinik olarak normal olduğu anlamına gelmez.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-4">
        {[
          ['Modalite', report.modality],
          ['Bölge', report.body_part],
          ['Bulgu cümlesi', String(report.findings.length)],
          ['Ölçüm', String(report.measurements.length)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-violet-200 bg-violet-50 p-5">
        <p className="text-xs font-bold uppercase tracking-wide text-violet-700">
          Yapılandırılmış özet
        </p>
        <p className="mt-3 text-sm leading-7 text-slate-700">{report.summary}</p>
        {report.impression ? (
          <div className="mt-4 rounded-lg border border-violet-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase text-slate-500">Rapor izlenimi / sonuç</p>
            <p className="mt-2 text-sm leading-6 text-slate-800">{report.impression}</p>
          </div>
        ) : null}
      </div>

      {report.measurements.length > 0 ? (
        <section>
          <h3 className="text-base font-semibold text-slate-950">Çıkarılan ölçümler</h3>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {report.measurements.map((measurement, index) => (
              <div
                key={`${measurement.value}-${measurement.unit}-${index}`}
                className="rounded-lg border border-cyan-200 bg-cyan-50 p-4"
              >
                <p className="font-semibold text-cyan-950">
                  {measurement.value} {measurement.unit}
                </p>
                <p className="mt-2 text-xs leading-5 text-slate-600">{measurement.context}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-slate-950">Bulgu cümleleri</h3>
          <p className="text-xs text-slate-500">
            {counts.critical} kritik · {counts.abnormal} anormal sinyal
          </p>
        </div>
        <div className="mt-3 space-y-3">
          {report.findings.map((finding, index) => (
            <article
              key={`${finding.text}-${index}`}
              className={`rounded-lg border p-4 ${findingClass(finding)}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm leading-6">{finding.text}</p>
                <span className="rounded-full border border-current/20 bg-white/70 px-2 py-1 text-[10px] font-bold uppercase">
                  {finding.classification}
                </span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <details className="rounded-xl border border-slate-200 bg-white p-4">
        <summary className="cursor-pointer text-sm font-semibold text-slate-800">
          Orijinal rapor metnini göster
        </summary>
        <pre className="mt-4 whitespace-pre-wrap break-words text-xs leading-6 text-slate-600">
          {report.original_text}
        </pre>
      </details>
    </div>
  );
}

export default function RadiologyPage() {
  const [mode, setMode] = useState<InputMode>('manual');
  const [reportDate, setReportDate] = useState(todayValue());
  const [modality, setModality] = useState('UNKNOWN');
  const [bodyPart, setBodyPart] = useState('OTHER');
  const [reportText, setReportText] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<RadiologyReport | null>(null);
  const [history, setHistory] = useState<RadiologyReport[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [error, setError] = useState('');

  const loadHistory = async () => {
    try {
      setIsHistoryLoading(true);
      setHistory(await listPatientRadiologyReports());
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Radyoloji geçmişi yüklenemedi.',
      );
    } finally {
      setIsHistoryLoading(false);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      const metadata = {
        reportDate: reportDate || null,
        modality: modality === 'UNKNOWN' ? null : modality,
        bodyPart: bodyPart === 'OTHER' ? null : bodyPart,
      };

      let report: RadiologyReport;
      if (mode === 'manual') {
        report = await createManualRadiologyReport({ ...metadata, reportText });
      } else {
        if (!selectedFile) {
          throw new Error('Önce bir radyoloji PDF dosyası seçmelisin.');
        }
        report = await uploadRadiologyReportPdf(selectedFile, metadata);
      }

      setResult(report);
      setHistory((current) => [
        report,
        ...current.filter((item) => item.id !== report.id),
      ]);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Radyoloji analizi başarısız.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Faz 2 · Radyoloji
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Radyoloji rapor analizi
        </h1>
        <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-500">
          Metin tabanlı radyoloji PDF&apos;lerini veya rapor metnini aynı MediCore hasta kaydına ekle. Sistem modaliteyi, bölgeyi, ölçümleri ve kritik terimleri yapılandırır.
        </p>
        <p className="mt-3 inline-flex rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
          Bu modül görüntünün kendisini yorumlamaz ve otomatik tanı üretmez. Çıktılar orijinal raporla hekim tarafından doğrulanmalıdır.
        </p>
      </header>

      <form onSubmit={submit} className="space-y-5">
        <SectionCard
          title="Rapor kaynağı"
          description="PDF yükle veya radyoloji raporunun metnini yapıştır. Taranmış PDF için OCR sonraki sürümde eklenecek."
        >
          <div className="flex flex-wrap gap-2">
            {([
              ['manual', 'Rapor metni'],
              ['pdf', 'PDF yükleme'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-lg px-4 py-2 text-sm font-semibold ${
                  mode === value
                    ? 'bg-blue-600 text-white'
                    : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-3">
            <label className="text-sm font-medium text-slate-700">
              Rapor tarihi
              <input
                type="date"
                value={reportDate}
                onChange={(event) => setReportDate(event.target.value)}
                className={INPUT_CLASS}
              />
            </label>
            <label className="text-sm font-medium text-slate-700">
              Modalite
              <select
                value={modality}
                onChange={(event) => setModality(event.target.value)}
                className={INPUT_CLASS}
              >
                {MODALITIES.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
            <label className="text-sm font-medium text-slate-700">
              Vücut bölgesi
              <select
                value={bodyPart}
                onChange={(event) => setBodyPart(event.target.value)}
                className={INPUT_CLASS}
              >
                {BODY_PARTS.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          </div>

          {mode === 'manual' ? (
            <label className="mt-5 block text-sm font-medium text-slate-700">
              Radyoloji raporu
              <textarea
                rows={14}
                minLength={10}
                maxLength={250000}
                required
                value={reportText}
                onChange={(event) => setReportText(event.target.value)}
                placeholder="Bulgular ve sonuç/izlenim bölümlerini buraya yapıştır..."
                className={`${INPUT_CLASS} resize-y leading-6`}
              />
              <span className="mt-1 block text-right text-xs text-slate-400">
                {reportText.length}/250000
              </span>
            </label>
          ) : (
            <label className="mt-5 block rounded-xl border border-dashed border-cyan-300 bg-cyan-50/50 p-5 text-sm font-medium text-slate-700">
              Metin tabanlı radyoloji PDF&apos;si
              <input
                type="file"
                accept="application/pdf,.pdf"
                required
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
                className="mt-3 block w-full text-sm"
              />
              {selectedFile ? (
                <span className="mt-2 block text-xs text-cyan-800">{selectedFile.name}</span>
              ) : null}
            </label>
          )}

          {error ? (
            <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isSubmitting}
            className="mt-5 rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? 'Analiz ediliyor…' : 'Raporu analiz et ve kaydet'}
          </button>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard
          title="Son analiz"
          description={`${formatDate(result.report_date)} · ${result.source_type}`}
        >
          <ReportResult report={result} />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Radyoloji geçmişi"
        description="Aynı demo hasta kaydına eklenen Faz 2 raporları."
        action={
          <button
            type="button"
            onClick={() => void loadHistory()}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Yenile
          </button>
        }
      >
        {isHistoryLoading ? (
          <p className="text-sm text-slate-500">Raporlar yükleniyor…</p>
        ) : history.length === 0 ? (
          <p className="text-sm text-slate-500">Henüz kaydedilmiş radyoloji raporu yok.</p>
        ) : (
          <div className="space-y-3">
            {history.map((report) => (
              <button
                key={report.id}
                type="button"
                onClick={() => setResult(report)}
                className="block w-full rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-blue-300 hover:bg-blue-50/30"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-slate-950">
                      {report.modality} · {report.body_part}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {formatDate(report.report_date)} · {report.file_name ?? 'Manuel rapor metni'}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    report.critical_findings.length > 0
                      ? 'bg-red-100 text-red-800'
                      : 'bg-emerald-100 text-emerald-800'
                  }`}>
                    {report.critical_findings.length > 0
                      ? `${report.critical_findings.length} kritik uyarı`
                      : 'Kritik terim yok'}
                  </span>
                </div>
                <p className="mt-3 text-sm leading-6 text-slate-600">
                  {report.impression ?? report.summary}
                </p>
              </button>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
