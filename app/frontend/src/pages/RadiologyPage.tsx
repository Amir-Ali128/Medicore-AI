import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';

import DexaMetricsPanel from '../components/clinical/DexaMetricsPanel';
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
  ['CT_WITH_CONTRAST', 'Kontrastlı BT'],
  ['CT_WITHOUT_CONTRAST', 'Kontrastsız BT'],
  ['CT', 'BT — kontrast bilgisi belirtilmemiş'],
  ['MRI', 'MR / MRI'],
  ['PET_CT', 'PET-BT'],
  ['DEXA', 'DEXA / DXA Kemik Yoğunluğu'],
] as const;

const BODY_PARTS = [
  ['OTHER', 'Otomatik belirle'],
  ['BONE_DENSITY', 'Kemik yoğunluğu / Çoklu bölge'],
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

function modalityLabel(value: string) {
  const labels: Record<string, string> = {
    XRAY: 'Röntgen',
    ULTRASOUND: 'Ultrasonografi',
    CT: 'BT',
    CT_WITH_CONTRAST: 'Kontrastlı BT',
    CT_WITHOUT_CONTRAST: 'Kontrastsız BT',
    MRI: 'MR',
    PET_CT: 'PET-BT',
    DEXA: 'DEXA',
    UNKNOWN: 'Belirlenemedi',
  };
  return labels[value] ?? value;
}

function bodyPartLabel(value: string) {
  const labels: Record<string, string> = {
    BONE_DENSITY: 'Kemik yoğunluğu',
    BRAIN: 'Beyin',
    CHEST: 'Toraks',
    ABDOMEN: 'Abdomen',
    PELVIS: 'Pelvis',
    SPINE: 'Omurga',
    NECK: 'Boyun',
    BREAST: 'Meme',
    CARDIAC: 'Kalp',
    MUSCULOSKELETAL: 'Kas-iskelet',
    WHOLE_BODY: 'Tüm vücut',
    OTHER: 'Diğer',
  };
  return labels[value] ?? value;
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

function findingLabel(finding: RadiologyFinding) {
  if (finding.is_critical || finding.classification === 'critical') return 'Kritik';
  if (finding.classification === 'abnormal') return 'Dikkat';
  return 'Bilgi';
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
          <p className="text-sm font-bold text-red-800">Kritik bulgular</p>
          <ul className="mt-3 space-y-2 text-sm font-semibold text-red-950">
            {report.critical_findings.map((finding) => (
              <li key={finding}>• {finding}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">
          Sistem kritik ifade saptamadı. Sonuç yine de hekim tarafından doğrulanmalıdır.
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ['Tetkik', modalityLabel(report.modality)],
          ['Bölge', bodyPartLabel(report.body_part)],
          ['Bulgu', String(report.findings.length)],
          ['Ölçüm', String(report.measurements.length)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-slate-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase text-slate-500">{label}</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-violet-200 bg-violet-50 p-5">
        <p className="text-sm font-bold text-violet-800">Rapor özeti</p>
        <p className="mt-3 text-sm leading-7 text-slate-700">{report.summary}</p>
        {report.impression ? (
          <div className="mt-4 rounded-lg border border-violet-200 bg-white p-4">
            <p className="text-xs font-semibold uppercase text-slate-500">Sonuç / izlenim</p>
            <p className="mt-2 text-sm leading-6 text-slate-800">{report.impression}</p>
          </div>
        ) : null}
      </div>

      <DexaMetricsPanel metrics={report.dexa_metrics} />

      {report.measurements.length > 0 ? (
        <section>
          <h3 className="font-semibold text-slate-950">Ölçümler</h3>
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
          <h3 className="font-semibold text-slate-950">Bulgular</h3>
          <p className="text-xs text-slate-500">
            {counts.critical} kritik · {counts.abnormal} dikkat gerektiren
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
                  {findingLabel(finding)}
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
  const fileInputRef = useRef<HTMLInputElement | null>(null);
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
  const [notice, setNotice] = useState('');

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

  function resetForm(showMessage = true) {
    setMode('manual');
    setReportDate(todayValue());
    setModality('UNKNOWN');
    setBodyPart('OTHER');
    setReportText('');
    setSelectedFile(null);
    setResult(null);
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (showMessage) {
      setNotice('Radyoloji giriş alanları temizlendi. Kaydedilmiş geçmiş raporlar korunuyor.');
      window.setTimeout(() => setNotice(''), 3000);
    }
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setNotice('');
    setIsSubmitting(true);

    try {
      const metadata = {
        reportDate: reportDate || null,
        modality: modality === 'UNKNOWN' ? null : modality,
        bodyPart: bodyPart === 'OTHER' ? null : bodyPart,
      };

      const report =
        mode === 'manual'
          ? await createManualRadiologyReport({ ...metadata, reportText })
          : selectedFile
            ? await uploadRadiologyReportPdf(selectedFile, metadata)
            : (() => {
                throw new Error('Önce bir radyoloji PDF dosyası seçmelisin.');
              })();

      setResult(report);
      setHistory((current) => [
        report,
        ...current.filter((item) => item.id !== report.id),
      ]);
      setNotice('Rapor analiz edildi ve hasta geçmişine kaydedildi.');
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
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">Radyoloji</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">Görüntüleme raporları</h1>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-500">
            Radyoloji veya DEXA raporunu ekleyin. Kaydedilen raporlar aktif hastanın geçmişinde tutulur.
          </p>
        </div>
        <button
          type="button"
          onClick={() => resetForm(true)}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Formu temizle
        </button>
      </header>

      {notice ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          {notice}
        </div>
      ) : null}

      <form onSubmit={submit} className="space-y-5">
        <SectionCard
          title="Yeni görüntüleme raporu"
          description="Rapor metnini yapıştırın veya metin içeren bir PDF yükleyin."
        >
          <div className="flex flex-wrap gap-2">
            {([
              ['manual', 'Rapor metni'],
              ['pdf', 'PDF yükle'],
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
              Tetkik türü
              <select
                value={modality}
                onChange={(event) => {
                  const nextModality = event.target.value;
                  setModality(nextModality);
                  if (nextModality === 'DEXA' && bodyPart === 'OTHER') {
                    setBodyPart('BONE_DENSITY');
                  }
                }}
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
              Rapor metni
              <textarea
                rows={14}
                minLength={10}
                maxLength={250000}
                required
                value={reportText}
                onChange={(event) => setReportText(event.target.value)}
                placeholder="Bulgular ve sonuç/izlenim bölümünü buraya yapıştırın..."
                className={`${INPUT_CLASS} resize-y leading-6`}
              />
            </label>
          ) : (
            <label className="mt-5 block rounded-xl border border-dashed border-cyan-300 bg-cyan-50/50 p-5 text-sm font-medium text-slate-700">
              Radyoloji / DEXA PDF dosyası
              <input
                ref={fileInputRef}
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

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              type="submit"
              disabled={isSubmitting}
              className="rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? 'Analiz ediliyor…' : 'Analiz et ve kaydet'}
            </button>
            <button
              type="button"
              onClick={() => resetForm(true)}
              className="rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Temizle
            </button>
          </div>
        </SectionCard>
      </form>

      {result ? (
        <SectionCard
          title="Son rapor"
          description={`${formatDate(result.report_date)} · ${modalityLabel(result.modality)}`}
        >
          <ReportResult report={result} />
        </SectionCard>
      ) : null}

      <SectionCard
        title="Görüntüleme geçmişi"
        description="Aktif hastaya kaydedilen radyoloji ve DEXA raporları."
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
          <p className="text-sm text-slate-500">Bu hasta için henüz görüntüleme raporu yok.</p>
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
                      {modalityLabel(report.modality)} · {bodyPartLabel(report.body_part)}
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
                      : 'Kritik uyarı yok'}
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
