import { useMemo, useState } from 'react';

import {
  normalizeSimpleCase,
  type LabInput,
  type MedicalReportInput,
  type SimpleCaseResponse,
} from '../services/simpleCaseClient';

type Step = 'clinical' | 'labs' | 'reports' | 'result';

const stepLabels: Record<Step, string> = {
  clinical: 'Klinik',
  labs: 'Laboratuvar',
  reports: 'Raporlar',
  result: 'Özet',
};

function splitLines(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function SimpleCaseWorkspacePage() {
  const [step, setStep] = useState<Step>('clinical');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState<'female' | 'male' | 'other' | 'unknown'>('unknown');
  const [complaints, setComplaints] = useState('');
  const [history, setHistory] = useState('');
  const [medications, setMedications] = useState('');
  const [notes, setNotes] = useState('');

  const [labs, setLabs] = useState<LabInput[]>([]);
  const [labDraft, setLabDraft] = useState({
    test_name: '',
    value: '',
    unit: '',
    source_reference: '',
  });

  const [reports, setReports] = useState<MedicalReportInput[]>([]);
  const [reportDraft, setReportDraft] = useState({
    report_type: '',
    body_region: '',
    findings: '',
    impression: '',
  });

  const [result, setResult] = useState<SimpleCaseResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const completed = useMemo(
    () => ({
      clinical: Boolean(age || complaints.trim() || history.trim()),
      labs: labs.length > 0,
      reports: reports.length > 0,
      result: Boolean(result),
    }),
    [age, complaints, history, labs.length, reports.length, result],
  );

  function addLab() {
    if (!labDraft.test_name.trim()) return;
    setLabs((current) => [
      ...current,
      {
        test_name: labDraft.test_name.trim(),
        value: labDraft.value.trim() || null,
        unit: labDraft.unit.trim() || null,
        source_reference: labDraft.source_reference.trim() || null,
        source_references: [],
      },
    ]);
    setLabDraft({ test_name: '', value: '', unit: '', source_reference: '' });
  }

  function addReport() {
    if (!reportDraft.report_type.trim()) return;
    setReports((current) => [
      ...current,
      {
        report_type: reportDraft.report_type.trim(),
        body_region: reportDraft.body_region.trim() || null,
        findings: reportDraft.findings.trim() || null,
        impression: reportDraft.impression.trim() || null,
        raw_text: null,
      },
    ]);
    setReportDraft({ report_type: '', body_region: '', findings: '', impression: '' });
  }

  async function evaluateCase() {
    setBusy(true);
    setError('');
    try {
      const response = await normalizeSimpleCase({
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
      });
      setResult(response);
      setStep('result');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Vaka işlenemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-5 py-5 sm:px-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">
                Yeni vaka
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
                Klinik veriyi tek yerde topla
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                Klinik bilgi, laboratuvar ve tetkik raporlarını ekle. MediCore kaynak veriyi koruyarak tek bir vaka yapısında birleştirir.
              </p>
            </div>

            <button
              type="button"
              onClick={evaluateCase}
              disabled={busy}
              className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? 'İşleniyor…' : 'Vakayı oluştur'}
            </button>
          </div>

          <div className="mt-6 grid grid-cols-4 gap-2">
            {(Object.keys(stepLabels) as Step[]).map((item, index) => (
              <button
                key={item}
                type="button"
                onClick={() => setStep(item)}
                className={[
                  'rounded-2xl px-3 py-3 text-left transition',
                  step === item
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-50 text-slate-600 hover:bg-slate-100',
                ].join(' ')}
              >
                <span className="block text-[10px] font-bold uppercase tracking-wider opacity-70">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="mt-1 block text-sm font-semibold">{stepLabels[item]}</span>
                <span className="mt-1 block text-xs opacity-70">
                  {completed[item] ? 'Hazır' : 'Bekliyor'}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="p-5 sm:p-7">
          {step === 'clinical' ? (
            <div className="grid gap-6 lg:grid-cols-[0.7fr_1.3fr]">
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Yaş</label>
                  <input
                    value={age}
                    onChange={(e) => setAge(e.target.value)}
                    inputMode="numeric"
                    placeholder="Örn. 58"
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-400 focus:bg-white"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cinsiyet</label>
                  <select
                    value={sex}
                    onChange={(e) => setSex(e.target.value as typeof sex)}
                    className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none focus:border-blue-400 focus:bg-white"
                  >
                    <option value="unknown">Belirtilmedi</option>
                    <option value="female">Kadın</option>
                    <option value="male">Erkek</option>
                    <option value="other">Diğer</option>
                  </select>
                </div>

                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">İlaçlar</label>
                  <textarea
                    value={medications}
                    onChange={(e) => setMedications(e.target.value)}
                    rows={4}
                    placeholder="Her satıra bir ilaç"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-400 focus:bg-white"
                  />
                </div>
              </div>

              <div className="grid gap-4">
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Şikayetler</label>
                  <textarea
                    value={complaints}
                    onChange={(e) => setComplaints(e.target.value)}
                    rows={5}
                    placeholder="Göğüs ağrısı, nefes darlığı, halsizlik…"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-400 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Özgeçmiş / Hastalıklar</label>
                  <textarea
                    value={history}
                    onChange={(e) => setHistory(e.target.value)}
                    rows={4}
                    placeholder="Hipertansiyon, diyabet, operasyon öyküsü…"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-400 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ek not</label>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={3}
                    placeholder="Hekim notu veya ek klinik bağlam"
                    className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-400 focus:bg-white"
                  />
                </div>
              </div>
            </div>
          ) : null}

          {step === 'labs' ? (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              <div className="rounded-3xl bg-slate-50 p-5">
                <h3 className="text-lg font-semibold text-slate-950">Laboratuvar sonucu ekle</h3>
                <p className="mt-1 text-sm text-slate-500">
                  Referansı laboratuvar raporunda yazdığı şekliyle gir.
                </p>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {([
                    ['test_name', 'Test adı', 'TSH'],
                    ['value', 'Sonuç', '2.1'],
                    ['unit', 'Birim', 'mIU/L'],
                    ['source_reference', 'Rapordaki referans', '0.27 - 4.20'],
                  ] as const).map(([key, label, placeholder]) => (
                    <label key={key} className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {label}
                      <input
                        value={labDraft[key]}
                        onChange={(e) => setLabDraft((current) => ({ ...current, [key]: e.target.value }))}
                        placeholder={placeholder}
                        className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-normal normal-case tracking-normal text-slate-950 outline-none focus:border-blue-400"
                      />
                    </label>
                  ))}
                </div>

                <button
                  type="button"
                  onClick={addLab}
                  className="mt-4 rounded-2xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  Sonucu ekle
                </button>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="font-semibold text-slate-950">Eklenen sonuçlar</h3>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                    {labs.length}
                  </span>
                </div>

                <div className="space-y-2">
                  {labs.length === 0 ? (
                    <div className="rounded-3xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                      Henüz laboratuvar sonucu eklenmedi.
                    </div>
                  ) : (
                    labs.map((lab, index) => (
                      <div key={`${lab.test_name}-${index}`} className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                        <div>
                          <p className="font-semibold text-slate-900">{lab.test_name}</p>
                          <p className="mt-1 text-sm text-slate-500">
                            {[lab.value, lab.unit, lab.source_reference ? `Ref: ${lab.source_reference}` : null]
                              .filter(Boolean)
                              .join(' · ')}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setLabs((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                          className="text-xs font-semibold text-red-500 hover:text-red-700"
                        >
                          Sil
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {step === 'reports' ? (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              <div className="rounded-3xl bg-slate-50 p-5">
                <h3 className="text-lg font-semibold text-slate-950">Tetkik raporu ekle</h3>
                <p className="mt-1 text-sm text-slate-500">
                  EKG, EKO, USG, BT, MR, röntgen ve diğer raporların hepsi aynı akışta.
                </p>

                <div className="mt-5 grid gap-3">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <input
                      value={reportDraft.report_type}
                      onChange={(e) => setReportDraft((c) => ({ ...c, report_type: e.target.value }))}
                      placeholder="Rapor türü · EKG / EKO / BT"
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    />
                    <input
                      value={reportDraft.body_region}
                      onChange={(e) => setReportDraft((c) => ({ ...c, body_region: e.target.value }))}
                      placeholder="Bölge · Toraks / Abdomen"
                      className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                    />
                  </div>
                  <textarea
                    value={reportDraft.findings}
                    onChange={(e) => setReportDraft((c) => ({ ...c, findings: e.target.value }))}
                    rows={5}
                    placeholder="Bulgular"
                    className="resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                  />
                  <textarea
                    value={reportDraft.impression}
                    onChange={(e) => setReportDraft((c) => ({ ...c, impression: e.target.value }))}
                    rows={3}
                    placeholder="Sonuç / Kanaat"
                    className="resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400"
                  />
                </div>

                <button
                  type="button"
                  onClick={addReport}
                  className="mt-4 rounded-2xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  Raporu ekle
                </button>
              </div>

              <div className="space-y-2">
                {reports.length === 0 ? (
                  <div className="rounded-3xl border border-dashed border-slate-200 p-8 text-center text-sm text-slate-400">
                    Henüz tetkik raporu eklenmedi.
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
                        </div>
                        <button
                          type="button"
                          onClick={() => setReports((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                          className="text-xs font-semibold text-red-500"
                        >
                          Sil
                        </button>
                      </div>
                      {report.impression ? (
                        <p className="mt-3 text-sm leading-6 text-slate-600">{report.impression}</p>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          ) : null}

          {step === 'result' ? (
            result ? (
              <div className="space-y-5">
                <div className="grid gap-3 sm:grid-cols-3">
                  {[
                    ['Klinik', result.clinical.complaints.length + result.clinical.history.length],
                    ['Lab', result.labs.length],
                    ['Rapor', result.reports.length],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-3xl bg-slate-50 p-5">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
                      <p className="mt-2 text-3xl font-semibold text-slate-950">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-3xl border border-slate-200 p-5">
                  <h3 className="font-semibold text-slate-950">Laboratuvar referansları</h3>
                  <div className="mt-4 divide-y divide-slate-100">
                    {result.labs.map((lab) => (
                      <div key={lab.test_name} className="grid gap-2 py-3 sm:grid-cols-[1fr_auto_auto] sm:items-center">
                        <span className="font-medium text-slate-900">{lab.test_name}</span>
                        <span className="text-sm text-slate-500">{[lab.value, lab.unit].filter(Boolean).join(' ')}</span>
                        <span className="text-sm font-medium text-slate-700">
                          {lab.reference_text ? `Ref: ${lab.reference_text}` : 'Referans yok'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {result.warnings.length > 0 ? (
                  <div className="rounded-3xl border border-amber-200 bg-amber-50 p-5">
                    <h3 className="font-semibold text-amber-950">Kontrol notları</h3>
                    <ul className="mt-3 space-y-2 text-sm text-amber-900">
                      {result.warnings.map((warning) => <li key={warning}>• {warning}</li>)}
                    </ul>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="rounded-3xl border border-dashed border-slate-200 p-10 text-center">
                <p className="text-sm text-slate-500">Henüz vaka oluşturulmadı.</p>
                <button
                  type="button"
                  onClick={evaluateCase}
                  className="mt-4 rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white"
                >
                  Vakayı oluştur
                </button>
              </div>
            )
          ) : null}

          {error ? (
            <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
