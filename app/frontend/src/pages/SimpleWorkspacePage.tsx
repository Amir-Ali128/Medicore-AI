import { useMemo, useState } from 'react';

import {
  normalizeSimpleCase,
  type LabResultInput,
  type MedicalReportInput,
  type SexValue,
  type SimpleCaseResponse,
} from '../services/simpleCaseClient';

const emptyLab = (): LabResultInput => ({
  test_name: '',
  value: '',
  unit: '',
  source_reference: '',
});

const emptyReport = (): MedicalReportInput => ({
  report_type: '',
  body_region: '',
  findings: '',
  impression: '',
  raw_text: '',
});

function splitLines(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function SimpleWorkspacePage() {
  const [age, setAge] = useState('');
  const [sex, setSex] = useState<SexValue>('unknown');
  const [complaints, setComplaints] = useState('');
  const [history, setHistory] = useState('');
  const [medications, setMedications] = useState('');
  const [notes, setNotes] = useState('');
  const [labs, setLabs] = useState<LabResultInput[]>([emptyLab()]);
  const [reports, setReports] = useState<MedicalReportInput[]>([emptyReport()]);
  const [result, setResult] = useState<SimpleCaseResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const readyLabCount = useMemo(
    () => labs.filter((item) => item.test_name.trim()).length,
    [labs],
  );
  const readyReportCount = useMemo(
    () => reports.filter((item) => item.report_type.trim()).length,
    [reports],
  );

  function updateLab(index: number, patch: Partial<LabResultInput>) {
    setLabs((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  }

  function updateReport(index: number, patch: Partial<MedicalReportInput>) {
    setReports((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  }

  async function evaluateCase() {
    setBusy(true);
    setError('');
    setResult(null);

    try {
      const response = await normalizeSimpleCase({
        clinical: {
          age: age.trim() ? Number(age) : null,
          sex,
          complaints: splitLines(complaints),
          history: splitLines(history),
          medications: splitLines(medications),
          notes: notes.trim() || null,
        },
        labs: labs.filter((item) => item.test_name.trim()),
        reports: reports.filter((item) => item.report_type.trim()),
      });
      setResult(response);
    } catch (evaluationError) {
      setError(
        evaluationError instanceof Error
          ? evaluationError.message
          : 'Vaka işlenemedi.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-6 py-6 sm:px-8">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">
                MediCore Workspace
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
                Klinik vaka tek ekranda
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 sm:text-base">
                Hasta bilgisini, laboratuvar sonuçlarını ve EKG/EKO/USG/BT/MR/Röntgen dahil
                tüm raporları tek vakada birleştir.
              </p>
            </div>

            <div className="flex gap-2 text-xs font-semibold text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-2">Lab {readyLabCount}</span>
              <span className="rounded-full bg-slate-100 px-3 py-2">Rapor {readyReportCount}</span>
            </div>
          </div>
        </div>

        <div className="grid gap-0 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="border-b border-slate-100 p-6 sm:p-8 lg:border-b-0 lg:border-r">
            <div className="mb-5">
              <p className="text-sm font-semibold text-slate-950">1 · Klinik bilgi</p>
              <p className="mt-1 text-sm text-slate-500">Sadece değerlendirmeye gerekli temel bağlam.</p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Yaş</span>
                <input
                  value={age}
                  onChange={(event) => setAge(event.target.value)}
                  inputMode="numeric"
                  placeholder="Örn. 54"
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-50"
                />
              </label>

              <label className="block">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cinsiyet</span>
                <select
                  value={sex}
                  onChange={(event) => setSex(event.target.value as SexValue)}
                  className="mt-2 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-50"
                >
                  <option value="unknown">Belirtilmedi</option>
                  <option value="female">Kadın</option>
                  <option value="male">Erkek</option>
                  <option value="other">Diğer</option>
                </select>
              </label>
            </div>

            {[
              ['Şikayetler', complaints, setComplaints, 'Göğüs ağrısı, nefes darlığı'],
              ['Öykü', history, setHistory, 'Hipertansiyon, diyabet'],
              ['İlaçlar', medications, setMedications, 'Aspirin, metformin'],
            ].map(([label, value, setter, placeholder]) => (
              <label key={label as string} className="mt-4 block">
                <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {label as string}
                </span>
                <textarea
                  value={value as string}
                  onChange={(event) => (setter as (value: string) => void)(event.target.value)}
                  placeholder={placeholder as string}
                  rows={2}
                  className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-50"
                />
              </label>
            ))}

            <label className="mt-4 block">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">Not</span>
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Ek klinik not..."
                rows={3}
                className="mt-2 w-full resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-50"
              />
            </label>
          </div>

          <div className="space-y-8 p-6 sm:p-8">
            <section>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-950">2 · Laboratuvar</p>
                  <p className="mt-1 text-sm text-slate-500">
                    Referansı laboratuvar raporunda yazdığı şekliyle gir.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setLabs((current) => [...current, emptyLab()])}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  + Sonuç
                </button>
              </div>

              <div className="space-y-3">
                {labs.map((lab, index) => (
                  <div key={index} className="grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 sm:grid-cols-[1.2fr_.7fr_.6fr_1.2fr_auto]">
                    <input
                      value={lab.test_name}
                      onChange={(event) => updateLab(index, { test_name: event.target.value })}
                      placeholder="Test adı"
                      className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                    <input
                      value={String(lab.value ?? '')}
                      onChange={(event) => updateLab(index, { value: event.target.value })}
                      placeholder="Değer"
                      className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                    <input
                      value={lab.unit ?? ''}
                      onChange={(event) => updateLab(index, { unit: event.target.value })}
                      placeholder="Birim"
                      className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                    <input
                      value={lab.source_reference ?? ''}
                      onChange={(event) => updateLab(index, { source_reference: event.target.value })}
                      placeholder="Rapordaki referans"
                      className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                    <button
                      type="button"
                      onClick={() => setLabs((current) => current.filter((_, i) => i !== index))}
                      className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-400 hover:bg-white hover:text-red-600"
                    >
                      Sil
                    </button>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-slate-950">3 · Tetkik raporları</p>
                  <p className="mt-1 text-sm text-slate-500">
                    EKG, EKO, USG, BT, MR, röntgen ve diğer raporlar aynı yapıda.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setReports((current) => [...current, emptyReport()])}
                  className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  + Rapor
                </button>
              </div>

              <div className="space-y-3">
                {reports.map((report, index) => (
                  <div key={index} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                      <input
                        value={report.report_type}
                        onChange={(event) => updateReport(index, { report_type: event.target.value })}
                        placeholder="Rapor türü · EKG / EKO / BT..."
                        className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                      />
                      <input
                        value={report.body_region ?? ''}
                        onChange={(event) => updateReport(index, { body_region: event.target.value })}
                        placeholder="Bölge · Toraks / abdomen..."
                        className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                      />
                      <button
                        type="button"
                        onClick={() => setReports((current) => current.filter((_, i) => i !== index))}
                        className="rounded-xl px-3 py-2 text-xs font-semibold text-slate-400 hover:bg-white hover:text-red-600"
                      >
                        Sil
                      </button>
                    </div>
                    <textarea
                      value={report.findings ?? ''}
                      onChange={(event) => updateReport(index, { findings: event.target.value })}
                      placeholder="Bulgular"
                      rows={3}
                      className="mt-2 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                    <textarea
                      value={report.impression ?? ''}
                      onChange={(event) => updateReport(index, { impression: event.target.value })}
                      placeholder="Sonuç / kanaat"
                      rows={2}
                      className="mt-2 w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-blue-400"
                    />
                  </div>
                ))}
              </div>
            </section>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50 px-6 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <p className="text-xs leading-5 text-slate-500">
            MediCore burada sınıflandırma yapmaz; laboratuvar referansını kaynaktan taşır.
          </p>
          <button
            type="button"
            onClick={evaluateCase}
            disabled={busy}
            className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? 'İşleniyor…' : 'Vakayı Hazırla'}
          </button>
        </div>
      </section>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {result ? (
        <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <div className="flex flex-col gap-2 border-b border-slate-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-600">Vaka Özeti</p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950">Kaynaklar normalize edildi</h2>
            </div>
            <span className="w-fit rounded-full bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700">
              {result.contract_version}
            </span>
          </div>

          <div className="mt-6 grid gap-5 lg:grid-cols-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Laboratuvar</h3>
              <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200">
                {result.labs.length ? result.labs.map((lab) => (
                  <div key={lab.test_name} className="grid grid-cols-[1fr_auto] gap-4 border-b border-slate-100 px-4 py-3 last:border-b-0">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{lab.test_name}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        Referans: {lab.reference_text ?? 'Kaynakta bulunamadı'}
                      </p>
                    </div>
                    <p className="text-sm font-semibold text-slate-900">
                      {String(lab.value ?? '—')} {lab.unit ?? ''}
                    </p>
                  </div>
                )) : (
                  <p className="px-4 py-5 text-sm text-slate-500">Laboratuvar sonucu eklenmedi.</p>
                )}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-slate-900">Tetkik raporları</h3>
              <div className="mt-3 space-y-3">
                {result.reports.length ? result.reports.map((report, index) => (
                  <article key={index} className="rounded-2xl border border-slate-200 p-4">
                    <p className="text-sm font-semibold text-slate-950">{report.report_type}</p>
                    {report.body_region ? <p className="mt-1 text-xs text-slate-500">{report.body_region}</p> : null}
                    {report.findings ? <p className="mt-3 text-sm leading-6 text-slate-700">{report.findings}</p> : null}
                    {report.impression ? <p className="mt-2 text-sm font-medium leading-6 text-slate-900">{report.impression}</p> : null}
                  </article>
                )) : (
                  <p className="rounded-2xl border border-slate-200 px-4 py-5 text-sm text-slate-500">Tetkik raporu eklenmedi.</p>
                )}
              </div>
            </div>
          </div>

          {result.warnings.length ? (
            <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-sm font-semibold text-amber-900">Kontrol notları</p>
              <ul className="mt-2 space-y-1 text-sm text-amber-800">
                {result.warnings.map((warning) => <li key={warning}>• {warning}</li>)}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
