import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiClientError } from '../services/apiClient';
import {
  getHbysStatus,
  importHbysEncounter,
  listHbysEncounters,
  sendHbysReport,
  type HbysEncounter,
  type HbysStatus,
} from '../services/hbysClient';

function errorText(error: unknown): string {
  if (error instanceof ApiClientError) {
    const body = error.body as { detail?: unknown } | undefined;
    if (typeof body?.detail === 'string') return body.detail;
  }
  return 'HBYS işlemi tamamlanamadı. Lütfen tekrar deneyin.';
}

function formatDate(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('tr-TR', { dateStyle: 'short', timeStyle: 'short' });
}

export default function HbysPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<HbysStatus | null>(null);
  const [encounters, setEncounters] = useState<HbysEncounter[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError('');
    try {
      const current = await getHbysStatus(signal);
      setStatus(current);
      setEncounters(current.reachable ? await listHbysEncounters(signal) : []);
    } catch (err) {
      if (!signal?.aborted) setError(errorText(err));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function handleImport(encounter: HbysEncounter) {
    setBusy(encounter.encounter_id);
    setError('');
    setMessage('');
    try {
      const patientId = await importHbysEncounter(encounter.encounter_id);
      navigate(`/case?patient=${encodeURIComponent(patientId)}&step=summary`);
    } catch (err) {
      setError(errorText(err));
      setBusy(null);
    }
  }

  async function handleSend(encounter: HbysEncounter) {
    if (!encounter.medicore_patient_id) return;
    setBusy(encounter.encounter_id);
    setError('');
    setMessage('');
    try {
      await sendHbysReport(encounter.encounter_id, encounter.medicore_patient_id);
      setMessage(`${encounter.protocol_no} için AI raporu HBYS'ye gönderildi (hekim onayı bekliyor).`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">HBYS Entegrasyonu</h1>
          <p className="mt-1 text-sm text-slate-500">
            Muayeneleri hastane sisteminden kimliksiz olarak aktarın; AI raporunu HBYS'ye geri gönderin.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Yenile
        </button>
      </header>

      <section className="rounded-3xl border border-slate-200 bg-white p-4 text-sm">
        {loading && !status ? (
          <p className="text-slate-500">HBYS bağlantısı kontrol ediliyor…</p>
        ) : !status ? (
          <p className="text-slate-500">Bağlantı durumu alınamadı; ayrıntı aşağıda.</p>
        ) : status.reachable ? (
          <p className="text-emerald-700">
            Bağlı: <b>{status.software ?? 'HBYS'}</b> · FHIR {status.fhir_version ?? '-'}
          </p>
        ) : (
          <p className="text-amber-700">
            HBYS'ye ulaşılamıyor. {status.detail ?? 'Sunucu ayarlarında HBYS_BASE_URL ve HBYS_API_KEY tanımlı olmalı.'}
          </p>
        )}
        <p className="mt-2 text-xs text-slate-500">
          Ad, T.C. kimlik no, telefon, adres ve doğum tarihi Medicore'a aktarılmaz; yalnızca protokol numarası, yaş,
          cinsiyet, klinik bulgular, laboratuvar ve radyoloji sonuçları gelir.
        </p>
      </section>

      {error ? <div role="alert" className="rounded-2xl bg-rose-50 p-3 text-sm text-rose-700">{error}</div> : null}
      {message ? <div role="status" className="rounded-2xl bg-emerald-50 p-3 text-sm text-emerald-700">{message}</div> : null}

      <section className="overflow-x-auto rounded-3xl border border-slate-200 bg-white">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3">Protokol No</th>
              <th className="px-4 py-3">Birim</th>
              <th className="px-4 py-3">Kabul</th>
              <th className="px-4 py-3">Durum</th>
              <th className="px-4 py-3">Tetkik</th>
              <th className="px-4 py-3 text-right">İşlem</th>
            </tr>
          </thead>
          <tbody>
            {encounters.map((encounter) => (
              <tr key={encounter.encounter_id} className="border-t border-slate-100">
                <td className="px-4 py-3 font-medium text-slate-900">{encounter.protocol_no}</td>
                <td className="px-4 py-3 text-slate-600">{encounter.department ?? '-'}</td>
                <td className="px-4 py-3 text-slate-600">{formatDate(encounter.admitted_at)}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                    {encounter.status === 'in-progress' ? 'Açık' : 'Kapandı'}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {encounter.lab_count} lab{encounter.radiology_count ? ` · ${encounter.radiology_count} radyoloji` : ''}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => void handleImport(encounter)}
                      className="rounded-xl bg-slate-950 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      {busy === encounter.encounter_id ? 'İşleniyor…' : encounter.medicore_patient_id ? 'Güncelle ve aç' : 'Aktar'}
                    </button>
                    {encounter.medicore_patient_id ? (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void handleSend(encounter)}
                        className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-50"
                      >
                        Raporu HBYS'ye gönder
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && status?.reachable && encounters.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-500">HBYS'de muayene bulunamadı.</td></tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}
