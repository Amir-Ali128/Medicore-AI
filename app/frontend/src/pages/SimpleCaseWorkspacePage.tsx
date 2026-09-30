import { useEffect, useMemo, useState } from 'react';

import {
  createPatient,
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
import { getActivePatientId, getPatientRecord } from '../services/patientClient';

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

export default function SimpleCaseWorkspacePage() {
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
  const [aiInterpretation, setAiInterpretation] = useState<CaseAIInterpretation | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const sessionPatientId = sessionStorage.getItem('medicore:case-patient-id');
    const activePatientId = sessionPatientId || getActivePatientId();
    if (!activePatientId) return;
    const patientIdToLoad: string = activePatientId;

    let cancelled = false;

    async function hydrateSavedCase() {
      setError('');
      try {
        const patient = await getPatientRecord(patientIdToLoad);
        if (cancelled) return;

        setPatientId(patient.id);
        setProtocolNo(patient.protocol_no);

        const metadata = (patient.metadata_json ?? {}) as Record<string, unknown>;
        const simpleCase = metadata.simple_case as
          | {
              clinical?: {
                age?: number | null;
                sex?: SexValue;
                complaints?: string[];
                history?: string[];
                medications?: string[];
                notes?: string | null;
              };
              labs?: Array<{
                test_name?: string;
                value?: string | number | null;
                unit?: string | null;
                measured_at?: string | null;
                reference_text?: string | null;
                reference_details?: {
                  text: string;
                  minimum?: number | null;
                  maximum?: number | null;
                  unit?: string | null;
                  age_min?: number | null;
                  age_max?: number | null;
                  sex?: SexValue | null;
                } | null;
                source_metadata?: Record<string, unknown>;
              }>;
              reports?: MedicalReportInput[];
              warnings?: string[];
              contract_version?: 'medicore-simple-case-v1';
            }
          | undefined;

        const clinical = simpleCase?.clinical;
        const fallbackAge =
          typeof metadata.age === 'number' ? metadata.age : null;

        setAge(
          clinical?.age !== null && clinical?.age !== undefined
            ? String(clinical.age)
            : fallbackAge !== null
              ? String(fallbackAge)
              : '',
        );
        setSex((clinical?.sex ?? patient.sex ?? 'unknown') as SexValue);
        setComplaints((clinical?.complaints ?? []).join('\n'));
        setHistory((clinical?.history ?? []).join('\n'));
        setMedications((clinical?.medications ?? []).join('\n'));
        setNotes(clinical?.notes ?? '');

        const restoredLabs: LabInput[] = (simpleCase?.labs ?? [])
          .filter((item) => Boolean(item.test_name))
          .map((item) => ({
            test_name: item.test_name ?? '',
            value: item.value ?? null,
            unit: item.unit ?? null,
            source_reference: item.reference_text ?? null,
            source_references: item.reference_details ? [item.reference_details] : [],
            source_metadata: item.source_metadata ?? {},
          }));

        setLabs(restoredLabs);
        setReports(simpleCase?.reports ?? []);

        if (simpleCase?.contract_version === 'medicore-simple-case-v1') {
          setResult({
            contract_version: 'medicore-simple-case-v1',
            clinical: {
              age: clinical?.age ?? null,
              sex: clinical?.sex ?? 'unknown',
              complaints: clinical?.complaints ?? [],
              history: clinical?.history ?? [],
              medications: clinical?.medications ?? [],
              notes: clinical?.notes ?? null,
            },
            labs: (simpleCase.labs ?? []).map((item) => ({
              test_name: item.test_name ?? '',
              value: item.value ?? null,
              unit: item.unit ?? null,
              reference_text: item.reference_text ?? null,
              reference_source: item.reference_text ? 'report' : 'missing',
            })),
            reports: simpleCase.reports ?? [],
            warnings: simpleCase.warnings ?? [],
          });
          setSaved(true);
        }

        const savedAi = metadata.simple_case_ai_report as
          | { report_text?: string; model?: string }
          | undefined;
        if (savedAi?.report_text) {
          setAiInterpretation({
            report_text: savedAi.report_text,
            model: savedAi.model ?? 'saved',
          });
        }

        const requestedStep = sessionStorage.getItem('medicore:case-open-step');
        sessionStorage.removeItem('medicore:case-open-step');
        sessionStorage.removeItem('medicore:case-patient-id');
        const validStep = steps.some((item) => item.key === requestedStep)
          ? (requestedStep as Step)
          : null;
        setStep(validStep ?? (savedAi?.report_text ? 'summary' : 'patient'));
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
  }, []);

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
    try {
      const interpretation = await interpretSimpleCase(payload, patientId);
      setAiInterpretation(interpretation);
      setStep('summary');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI klinik yorum tamamlanamadı.');
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

                  <div className="mt-5 whitespace-pre-wrap font-serif text-[15px] leading-8 text-slate-800">
                    {aiInterpretation.report_text}
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
