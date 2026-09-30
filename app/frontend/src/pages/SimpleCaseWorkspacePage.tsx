import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import {
  createPatient,
  getSavedSimpleCase,
  interpretSimpleCase,
  saveSimpleCase,
  uploadLabPdf,
  uploadReportPdf,
  type CaseAIInterpretation,
  type LabInput,
  type MedicalReportInput,
  type SexValue,
  type SimpleCaseRequest,
  type SimpleCaseResponse,
} from '../services/simpleCaseClient';
import { getActivePatientId } from '../services/patientClient';
import { simpleCaseInputKey } from '../services/simpleCaseInputKey';

type Step = 'patient' | 'clinical' | 'labs' | 'reports' | 'summary';

const steps: Array<{ key: Step; label: string }> = [
  { key: 'patient', label: 'Hasta' },
  { key: 'clinical', label: 'Klinik' },
  { key: 'labs', label: 'Kan PDF' },
  { key: 'reports', label: 'Rapor PDF' },
  { key: 'summary', label: 'Özet' },
];

function splitLines(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function fileNameFromMetadata(metadata?: Record<string, unknown>) {
  const value = metadata?.source_file_name;
  return typeof value === 'string' ? value : null;
}

const CURRENT_REPORT_HEADINGS = [
  'KLİNİK ÖZET',
  'ÖNE ÇIKAN LABORATUVAR BULGULARI',
  'TETKİK / RAPOR BULGULARI',
  'ENTEGRE KLİNİK DEĞERLENDİRME',
  'OLASI KLİNİK DURUMLAR / AYIRICI TANI',
  'ÖNERİLEN İLERİ TETKİK / İZLEM',
  'SONUÇ / KANAAT',
  'HEKİM NOTU',
] as const;

const REPORT_HEADINGS = [
  ...CURRENT_REPORT_HEADINGS,
  // Older saved reports remain readable, but are marked as legacy in the UI.
  'KLİNİK BİLGİ',
  'LABORATUVAR DEĞERLENDİRMESİ',
] as const;

function isCurrentClinicalReport(text: string | null | undefined) {
  if (!text?.trim()) return false;
  const upper = text.toLocaleUpperCase('tr-TR');
  return CURRENT_REPORT_HEADINGS.every((heading) => upper.includes(heading));
}

function parseClinicalReport(text: string) {
  const normalized = text.replace(/\r\n/g, '\n').trim();
  const upper = normalized.toLocaleUpperCase('tr-TR');
  const matches = REPORT_HEADINGS
    .map((heading) => ({ heading, index: upper.indexOf(heading) }))
    .filter((item) => item.index >= 0)
    .sort((a, b) => a.index - b.index);

  if (matches.length === 0) {
    return [{ heading: 'KLİNİK DEĞERLENDİRME', body: normalized }];
  }

  return matches.map((item, index) => {
    const start = item.index + item.heading.length;
    const end = matches[index + 1]?.index ?? normalized.length;
    return {
      heading: item.heading,
      body: normalized.slice(start, end).replace(/^\s*[:\-]?\s*/, '').trim(),
    };
  }).filter((section) => section.body);
}

function ReportSection({ heading, body }: { heading: string; body: string }) {
  const emphasis =
    heading.includes('AYIRICI TANI') || heading.includes('İLERİ TETKİK')
      ? 'border-blue-200 bg-blue-50/40'
      : heading.includes('SONUÇ')
        ? 'border-slate-300 bg-slate-50'
        : 'border-slate-200 bg-white';

  const lines = body
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  const listLike = lines.length > 1 && lines.some((line) => /^[-•*]|^\d+[.)]/.test(line));

  return (
    <section className={`rounded-3xl border p-5 sm:p-6 ${emphasis}`}>
      <h4 className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
        {heading}
      </h4>
      {listLike ? (
        <div className="mt-4 space-y-3">
          {lines.map((line, index) => (
            <div
              key={`${heading}-${index}`}
              className="rounded-2xl border border-slate-200/80 bg-white px-4 py-3 text-sm leading-6 text-slate-800"
            >
              {line.replace(/^[-•*]\s*/, '')}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 whitespace-pre-line text-sm leading-7 text-slate-700">
          {body}
        </div>
      )}
    </section>
  );
}

export default function SimpleCaseWorkspacePage() {
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState<Step>('patient');

  const [protocolNo, setProtocolNo] = useState('');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState<SexValue>('unknown');
  const [patientId, setPatientId] = useState<string | null>(null);

  const [complaints, setComplaints] = useState('');
  const [history, setHistory] = useState('');
  const [medications, setMedications] = useState('');
  const [notes, setNotes] = useState('');

  const [labs, setLabs] = useState<LabInput[]>([]);
  const [labBusy, setLabBusy] = useState(false);

  const [reports, setReports] = useState<MedicalReportInput[]>([]);
  const [reportType, setReportType] = useState('Tıbbi Rapor');
  const [bodyRegion, setBodyRegion] = useState('');
  const [reportBusy, setReportBusy] = useState(false);

  const [result, setResult] = useState<SimpleCaseResponse | null>(null);
  const [aiResult, setAiResult] = useState<{
    report: CaseAIInterpretation;
    inputKey: string;
  } | null>(null);
  const [aiReportWarning, setAiReportWarning] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const requestedPatientId = searchParams.get('patient');
    const activePatientId = requestedPatientId || getActivePatientId();
    if (!activePatientId) return;
    const patientIdToLoad: string = activePatientId;

    let cancelled = false;

    async function hydrateSavedCase() {
      setError('');
      setAiReportWarning('');
      try {
        const saved = await getSavedSimpleCase(patientIdToLoad);
        if (cancelled) return;

        setPatientId(saved.patient_id);
        setProtocolNo(saved.protocol_no);

        const simpleCase = saved.simple_case;
        const clinical = simpleCase?.clinical;

        setAge(
          clinical?.age !== null && clinical?.age !== undefined
            ? String(clinical.age)
            : saved.age !== null && saved.age !== undefined
              ? String(saved.age)
              : '',
        );
        setSex((clinical?.sex ?? saved.sex ?? 'unknown') as SexValue);
        setComplaints((clinical?.complaints ?? []).join('\n'));
        setHistory((clinical?.history ?? []).join('\n'));
        setMedications((clinical?.medications ?? []).join('\n'));
        setNotes(clinical?.notes ?? '');

        const restoredLabs: LabInput[] = (simpleCase?.labs ?? []).map((item) => ({
          test_name: item.test_name,
          value: item.value,
          unit: item.unit,
          measured_at: item.measured_at,
          source_reference: item.reference_text,
          source_references: item.reference_details ? [item.reference_details] : [],
          source_metadata: item.source_metadata ?? {},
        }));

        setLabs(restoredLabs);
        setReports(simpleCase?.reports ?? []);

        if (simpleCase) {
          setResult({
            contract_version: simpleCase.contract_version,
            clinical: simpleCase.clinical,
            labs: simpleCase.labs.map((item) => ({
              test_name: item.test_name,
              value: item.value,
              unit: item.unit,
              reference_text: item.reference_text,
              reference_source: item.reference_source,
            })),
            reports: simpleCase.reports,
            warnings: simpleCase.warnings,
          });
          setSaved(true);
        } else {
          setResult(null);
          setSaved(false);
        }

        setAiResult(saved.ai_report && simpleCase ? {
          report: saved.ai_report,
          inputKey: simpleCaseInputKey(saved.patient_id, {
            clinical: simpleCase.clinical,
            labs: restoredLabs,
            reports: simpleCase.reports,
          }),
        } : null);
        if (saved.ai_report && !isCurrentClinicalReport(saved.ai_report.report_text)) {
          setAiReportWarning(
            'Bu kayıt eski rapor formatında. Güncel klinik rapor için “Yeniden yorumla” düğmesini kullan.',
          );
        }

        const requestedStep = searchParams.get('step') as Step | null;
        const validStep = steps.some((item) => item.key === requestedStep)
          ? (requestedStep as Step)
          : null;
        setStep(validStep ?? (saved.ai_report ? 'summary' : simpleCase ? 'clinical' : 'patient'));
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Kayıtlı vaka açılamadı.');
        }
      }
    }

    void hydrateSavedCase();
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  const payload = useMemo<SimpleCaseRequest>(
    () => ({
      clinical: {
        age: age ? Number(age) : null,
        sex,
        complaints: splitLines(complaints),
        history: splitLines(history),
        medications: splitLines(medications),
        notes: notes.trim() || null,
      },
      labs,
      reports,
    }),
    [age, sex, complaints, history, medications, notes, labs, reports],
  );

  // Hide responses produced for earlier inputs, including late AI responses.
  const inputKey = simpleCaseInputKey(patientId, payload);
  const aiInterpretation = aiResult?.inputKey === inputKey ? aiResult.report : null;

  const completed = {
    patient: Boolean(patientId),
    clinical: Boolean(complaints.trim() || history.trim() || medications.trim() || notes.trim()),
    labs: labs.length > 0,
    reports: reports.length > 0,
    summary: Boolean(result || saved),
  };

  async function savePatient() {
    if (!protocolNo.trim()) {
      setError('Hasta için bir protokol numarası gir.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const patient = await createPatient({
        protocol_no: protocolNo.trim(),
        age: age ? Number(age) : null,
        sex,
        clinical_context: payload.clinical,
      });
      setPatientId(patient.id);
      setSaved(false);
      setStep('clinical');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Hasta kaydedilemedi.');
    } finally {
      setSaving(false);
    }
  }

  async function handleLabPdf(file: File | null) {
    if (!file) return;
    setLabBusy(true);
    setError('');
    try {
      const rows = await uploadLabPdf(file);
      setLabs((current) => [...current, ...rows]);
      setSaved(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Kan PDF’i işlenemedi.');
    } finally {
      setLabBusy(false);
    }
  }

  async function handleReportPdf(file: File | null) {
    if (!file) return;
    setReportBusy(true);
    setError('');
    try {
      const report = await uploadReportPdf(file, reportType, bodyRegion);
      setReports((current) => [...current, report]);
      setSaved(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Rapor PDF’i işlenemedi.');
    } finally {
      setReportBusy(false);
    }
  }

  async function runAIInterpretation() {
    setAiBusy(true);
    setError('');
    setAiReportWarning('');
    const previousInterpretation = aiInterpretation;
    try {
      const interpretation = await interpretSimpleCase(payload, patientId);
      if (!isCurrentClinicalReport(interpretation.report_text)) {
        throw new Error('AI klinik raporu güncel bölüm sözleşmesini tamamlamadı.');
      }
      setAiResult({ report: interpretation, inputKey });
      setStep('summary');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI klinik yorum tamamlanamadı.';
      if (previousInterpretation) {
        setAiReportWarning(
          `Yeni AI raporu üretilemedi. Aşağıdaki rapor önceki kayıt; güncel çıktı değildir. ${message}`,
        );
      }
      setError(message);
    } finally {
      setAiBusy(false);
    }
  }

  async function saveCase() {
    if (!patientId) {
      setError('Önce hasta kaydını oluştur.');
      setStep('patient');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const normalized = await saveSimpleCase(patientId, payload);
      setResult(normalized);
      setSaved(true);
      setStep('summary');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vaka kaydedilemedi.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="overflow-hidden rounded-[30px] border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-6 sm:px-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">
                Yeni vaka
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">
                Hastayı kaydet, PDF’leri ekle, vakayı oluştur
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                Hasta ve klinik bilgileri manuel girilir. Kan sonuçları ve tetkik raporları PDF olarak yüklenir.
              </p>
            </div>

            <button
              type="button"
              onClick={saveCase}
              disabled={saving || !patientId}
              className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? 'Kaydediliyor…' : saved ? '✓ Vaka kaydedildi' : 'Vakayı kaydet'}
            </button>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {steps.map((item, index) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setStep(item.key)}
                className={[
                  'rounded-2xl px-3 py-3 text-left transition',
                  step === item.key
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-50 text-slate-600 hover:bg-slate-100',
                ].join(' ')}
              >
                <span className="block text-[10px] font-bold uppercase tracking-wider opacity-70">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="mt-1 block text-sm font-semibold">{item.label}</span>
                <span className="mt-1 block text-xs opacity-70">
                  {completed[item.key] ? 'Hazır' : 'Bekliyor'}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="p-5 sm:p-7">
          {step === 'patient' ? (
            <div className="grid gap-6 lg:grid-cols-[1fr_0.8fr]">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">Hasta bilgileri</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Bu bölüm manuel girilir ve hasta kaydı oluşturulur.
                </p>

                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500 sm:col-span-1">
                    Protokol No
                    <input
                      value={protocolNo}
                      onChange={(e) => setProtocolNo(e.target.value)}
                      placeholder="MC-2026-001"
                      disabled={Boolean(patientId)}
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400 disabled:opacity-60"
                    />
                  </label>

                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Yaş
                    <input
                      value={age}
                      onChange={(e) => setAge(e.target.value)}
                      inputMode="numeric"
                      placeholder="58"
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                    />
                  </label>

                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Cinsiyet
                    <select
                      value={sex}
                      onChange={(e) => setSex(e.target.value as SexValue)}
                      className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                    >
                      <option value="unknown">Belirtilmedi</option>
                      <option value="female">Kadın</option>
                      <option value="male">Erkek</option>
                      <option value="other">Diğer</option>
                    </select>
                  </label>
                </div>

                <button
                  type="button"
                  onClick={savePatient}
                  disabled={saving || Boolean(patientId)}
                  className="mt-5 rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {patientId ? '✓ Hasta kaydedildi' : saving ? 'Kaydediliyor…' : 'Hasta kaydını oluştur'}
                </button>
              </div>

              <div className="rounded-3xl bg-slate-50 p-5">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Kayıt durumu</p>
                <p className="mt-3 text-lg font-semibold text-slate-950">
                  {patientId ? 'Hasta hazır' : 'Hasta kaydı bekleniyor'}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {patientId
                    ? 'Bu vaka artık bu hasta kaydına bağlanabilir.'
                    : 'Önce hasta kaydını oluştur. Sonraki PDF’ler ve klinik bilgiler bu vakaya bağlanır.'}
                </p>
              </div>
            </div>
          ) : null}

          {step === 'clinical' ? (
            <div>
              <h2 className="text-xl font-semibold text-slate-950">Klinik bilgi</h2>
              <p className="mt-1 text-sm text-slate-500">Şikayet ve öykü manuel girilir.</p>

              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Şikayetler
                  <textarea
                    value={complaints}
                    onChange={(e) => { setComplaints(e.target.value); setSaved(false); }}
                    rows={5}
                    placeholder="Göğüs ağrısı, nefes darlığı, halsizlik…"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                  />
                </label>

                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Özgeçmiş / Hastalıklar
                  <textarea
                    value={history}
                    onChange={(e) => { setHistory(e.target.value); setSaved(false); }}
                    rows={5}
                    placeholder="Hipertansiyon, diyabet, operasyon öyküsü…"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                  />
                </label>

                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  İlaçlar
                  <textarea
                    value={medications}
                    onChange={(e) => { setMedications(e.target.value); setSaved(false); }}
                    rows={4}
                    placeholder="Her satıra bir ilaç"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                  />
                </label>

                <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Ek klinik not
                  <textarea
                    value={notes}
                    onChange={(e) => { setNotes(e.target.value); setSaved(false); }}
                    rows={4}
                    placeholder="Muayene veya hekim notu"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                  />
                </label>
              </div>

              <button
                type="button"
                onClick={() => setStep('labs')}
                className="mt-5 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
              >
                Klinik bilgiyi kaydet ve devam et
              </button>
            </div>
          ) : null}

          {step === 'labs' ? (
            <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">Kan sonuçları</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Kan sonuçları manuel yazılmaz; laboratuvar PDF’ini yükle.
                </p>

                <label className="mt-5 block cursor-pointer rounded-3xl border-2 border-dashed border-blue-200 bg-blue-50/60 p-7 text-center transition hover:border-blue-300 hover:bg-blue-50">
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    disabled={labBusy}
                    onChange={(e) => void handleLabPdf(e.target.files?.[0] ?? null)}
                  />
                  <span className="block text-3xl">↑</span>
                  <span className="mt-3 block font-semibold text-slate-950">
                    {labBusy ? 'PDF okunuyor…' : 'Kan tahlili PDF yükle'}
                  </span>
                  <span className="mt-1 block text-xs text-slate-500">
                    Sonuç, birim ve raporda yazan referans otomatik çıkarılır.
                  </span>
                </label>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-semibold text-slate-950">Çıkarılan sonuçlar</h3>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                    {labs.length}
                  </span>
                </div>

                <div className="max-h-[32rem] space-y-2 overflow-y-auto pr-1">
                  {labs.length === 0 ? (
                    <div className="rounded-3xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                      Henüz kan PDF’i yüklenmedi.
                    </div>
                  ) : (
                    labs.map((lab, index) => (
                      <div key={`${lab.test_name}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="font-semibold text-slate-950">{lab.test_name}</p>
                            <p className="mt-1 text-sm text-slate-500">
                              {[lab.value, lab.unit].filter(Boolean).join(' ')}
                              {lab.source_reference ? ` · Ref: ${lab.source_reference}` : ' · Referans yok'}
                            </p>
                            {fileNameFromMetadata(lab.source_metadata) ? (
                              <p className="mt-1 text-xs text-slate-400">
                                {fileNameFromMetadata(lab.source_metadata)}
                              </p>
                            ) : null}
                          </div>
                          <button
                            type="button"
                            onClick={() => { setLabs((current) => current.filter((_, i) => i !== index)); setSaved(false); }}
                            className="text-xs font-semibold text-red-500"
                          >
                            Sil
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {step === 'reports' ? (
            <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
              <div>
                <h2 className="text-xl font-semibold text-slate-950">Tetkik raporları</h2>
                <p className="mt-1 text-sm text-slate-500">
                  EKG, EKO, USG, BT, MR, röntgen ve diğer yazılı raporları PDF olarak yükle.
                </p>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <input
                    value={reportType}
                    onChange={(e) => setReportType(e.target.value)}
                    placeholder="Rapor türü · EKG / EKO / BT"
                    className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-400"
                  />
                  <input
                    value={bodyRegion}
                    onChange={(e) => setBodyRegion(e.target.value)}
                    placeholder="Bölge · Toraks / Abdomen"
                    className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none focus:border-blue-400"
                  />
                </div>

                <label className="mt-4 block cursor-pointer rounded-3xl border-2 border-dashed border-violet-200 bg-violet-50/60 p-7 text-center transition hover:border-violet-300">
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    className="hidden"
                    disabled={reportBusy}
                    onChange={(e) => void handleReportPdf(e.target.files?.[0] ?? null)}
                  />
                  <span className="block text-3xl">↑</span>
                  <span className="mt-3 block font-semibold text-slate-950">
                    {reportBusy ? 'PDF okunuyor…' : 'Tetkik raporu PDF yükle'}
                  </span>
                </label>
              </div>

              <div className="space-y-2">
                {reports.length === 0 ? (
                  <div className="rounded-3xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                    Henüz rapor PDF’i yüklenmedi.
                  </div>
                ) : (
                  reports.map((report, index) => (
                    <div key={`${report.report_type}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="font-semibold text-slate-950">{report.report_type}</p>
                          <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">
                            {report.body_region || 'Bölge belirtilmedi'}
                          </p>
                          {fileNameFromMetadata(report.metadata) ? (
                            <p className="mt-2 text-xs text-slate-400">
                              {fileNameFromMetadata(report.metadata)}
                            </p>
                          ) : null}
                        </div>
                        <button
                          type="button"
                          onClick={() => { setReports((current) => current.filter((_, i) => i !== index)); setSaved(false); }}
                          className="text-xs font-semibold text-red-500"
                        >
                          Sil
                        </button>
                      </div>
                      {report.findings ? (
                        <p className="mt-3 line-clamp-4 whitespace-pre-line text-sm leading-6 text-slate-600">
                          {report.findings}
                        </p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}

          {step === 'summary' ? (
            <div className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-4">
                {[
                  ['Hasta', patientId ? 'Kayıtlı' : 'Bekliyor'],
                  ['Klinik', completed.clinical ? 'Hazır' : 'Boş'],
                  ['Kan', labs.length],
                  ['Rapor', reports.length],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-3xl bg-slate-50 p-5">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
                    <p className="mt-2 text-2xl font-semibold text-slate-950">{value}</p>
                  </div>
                ))}
              </div>

              <div className="rounded-3xl border border-slate-200 p-5">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-950">AI Klinik Yorum</h3>
                    <p className="mt-1 text-sm leading-6 text-slate-500">
                      Klinik bilgi, laboratuvar sonuçları ve tüm tetkik raporları birlikte değerlendirilir.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={runAIInterpretation}
                    disabled={aiBusy || (!completed.clinical && labs.length === 0 && reports.length === 0)}
                    className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {aiBusy ? 'AI değerlendiriyor…' : aiInterpretation ? 'Yeniden yorumla' : 'AI Klinik Yorum'}
                  </button>
                </div>
              </div>

              {aiReportWarning ? (
                <div className="rounded-3xl border border-amber-300 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-950">
                  <strong>AI rapor durumu:</strong> {aiReportWarning}
                </div>
              ) : null}

              {aiInterpretation ? (
                <div className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
                  <div className="flex flex-col gap-2 border-b border-slate-100 pb-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">
                      MediCore Klinik Değerlendirme Raporu
                    </p>
                    <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                      AI destekli hekim raporu
                    </h3>
                    <p className="text-xs text-slate-400">
                      Kaynak: klinik bilgi + laboratuvar + tetkik raporları
                    </p>
                  </div>

                  <div className="mt-5 grid gap-4">
                    {parseClinicalReport(aiInterpretation.report_text).map((section) => (
                      <ReportSection
                        key={section.heading}
                        heading={section.heading}
                        body={section.body}
                      />
                    ))}
                  </div>

                  <div className="mt-6 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-400">
                    Bu çıktı klinik karar desteği amacıyla oluşturulmuştur ve hekim değerlendirmesi ile doğrulanmalıdır.
                  </div>
                </div>
              ) : null}

              <div className="rounded-3xl border border-slate-200 p-5">
                <h3 className="font-semibold text-slate-950">Vaka durumu</h3>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {saved
                    ? 'Vaka hasta kaydına kaydedildi. Klinik bilgi, kan sonuçları ve raporlar aynı snapshot içinde tutuluyor.'
                    : 'Değişiklikleri hasta kaydına yazmak için “Vakayı kaydet” düğmesine bas.'}
                </p>
              </div>

              {result?.warnings?.length ? (
                <div className="rounded-3xl border border-amber-200 bg-amber-50 p-5">
                  <h3 className="font-semibold text-amber-950">Kontrol notları</h3>
                  <ul className="mt-3 space-y-2 text-sm text-amber-900">
                    {result.warnings.map((warning) => <li key={warning}>• {warning}</li>)}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {error ? (
            <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
