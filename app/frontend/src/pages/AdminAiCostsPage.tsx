import { useCallback, useEffect, useState } from 'react';

import { getStoredUser } from '../services/authClient';
import {
  getAiCostAnalytics,
  type AiCostAnalyticsResponse,
} from '../services/aiCostAnalyticsClient';

const WINDOW_OPTIONS = [
  { label: 'Son 1 saat', value: 60 },
  { label: 'Son 24 saat', value: 1440 },
  { label: 'Son 7 gün', value: 10080 },
  { label: 'Son 30 gün', value: 43200 },
];

function formatUsd(value: number | null | undefined) {
  if (value == null) return '—';
  return `$${value.toFixed(value < 0.01 ? 6 : 4)}`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
}

export default function AdminAiCostsPage() {
  const user = getStoredUser();
  const [minutes, setMinutes] = useState(1440);
  const [data, setData] = useState<AiCostAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (user?.role !== 'admin') return;
    try {
      setLoading(true);
      const response = await getAiCostAnalytics(minutes, 200);
      setData(response);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'AI kullanım verisi alınamadı.');
    } finally {
      setLoading(false);
    }
  }, [minutes, user?.role]);

  useEffect(() => {
    void load();
  }, [load]);

  if (user?.role !== 'admin') {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Yalnızca yönetici erişimi</h2>
        <p className="mt-2 text-sm text-amber-800">AI kullanım ve maliyet bilgileri yalnızca yönetici hesabına açıktır.</p>
      </section>
    );
  }

  const latestTracked = data?.events.find((event) => event.estimated_cost_usd != null) ?? null;

  return (
    <section className="space-y-5 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">Yönetici</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">AI kullanımı ve maliyet</h2>
          <p className="mt-1 text-sm text-slate-500">Claude çağrılarının gerçek token kullanımı ve token fiyatlarından hesaplanan USD maliyeti.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-sm font-medium text-slate-700">
            Zaman aralığı
            <select
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
              className="mt-1 block rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
            >
              {WINDOW_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => void load()} className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800">
            Yenile
          </button>
        </div>
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          ['Toplam maliyet', formatUsd(data?.estimated_cost_usd)],
          ['Claude çağrısı', data?.tracked_calls ?? 0],
          ['Input token', data?.input_tokens ?? 0],
          ['Output token', data?.output_tokens ?? 0],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
            <p className="text-xs text-slate-500 sm:text-sm">{label}</p>
            <p className="mt-2 break-words text-xl font-semibold text-slate-950 sm:text-2xl">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-violet-200 bg-violet-50/60 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">Son ölçülen çağrı</p>
          <p className="mt-2 text-2xl font-semibold text-violet-950">{formatUsd(latestTracked?.estimated_cost_usd)}</p>
          <p className="mt-1 text-xs text-violet-800">
            {latestTracked ? `${latestTracked.input_tokens ?? 0} input · ${latestTracked.output_tokens ?? 0} output` : 'Henüz ölçülen çağrı yok.'}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Fallback</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">{data?.fallback_count ?? 0}</p>
          <p className="mt-1 text-xs text-slate-500">Claude sonucu olmadan deterministik çıktı üretilen kayıt.</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Fiyat</p>
          <p className="mt-2 text-sm font-semibold text-slate-950">
            ${data?.pricing.input_per_million_usd ?? 2}/M input · ${data?.pricing.output_per_million_usd ?? 10}/M output
          </p>
          <p className="mt-1 text-xs text-slate-500">{data?.pricing.model ?? 'claude-sonnet-5'}</p>
        </div>
      </div>

      {(data?.untracked_ai_calls ?? 0) > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <strong>{data?.untracked_ai_calls} eski AI çağrısında token usage kaydı yok.</strong> Ölçüm yalnızca bu özellik deploy edildikten sonraki başarılı Claude çağrıları için kesin token sayılarını gösterebilir.
        </div>
      ) : null}

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3 sm:px-5">
          <h3 className="font-semibold text-slate-950">Çağrı geçmişi</h3>
          <p className="mt-1 text-xs text-slate-500">Hasta verisi gösterilmez; yalnızca kullanım ve maliyet metrikleri listelenir.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Zaman</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Input</th>
                <th className="px-4 py-3">Output</th>
                <th className="px-4 py-3">Maliyet</th>
                <th className="px-4 py-3">Durum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.events.map((event) => (
                <tr key={event.id}>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDate(event.created_at)}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-800">{event.model ?? '—'}</td>
                  <td className="px-4 py-3 text-slate-700">{event.input_tokens ?? '—'}</td>
                  <td className="px-4 py-3 text-slate-700">{event.output_tokens ?? '—'}</td>
                  <td className="px-4 py-3 font-semibold text-slate-900">{formatUsd(event.estimated_cost_usd)}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${event.ai_called ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}>
                      {event.ai_called ? (event.estimated_cost_usd != null ? 'Ölçüldü' : 'Eski / ölçümsüz') : 'Fallback'}
                    </span>
                  </td>
                </tr>
              ))}
              {!loading && (data?.events.length ?? 0) === 0 ? (
                <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-500">Bu aralıkta kompakt değerlendirme yok.</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      {loading ? <p className="text-xs text-slate-400">Yükleniyor…</p> : null}
    </section>
  );
}
