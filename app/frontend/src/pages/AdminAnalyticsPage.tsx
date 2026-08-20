import { useCallback, useEffect, useMemo, useState } from 'react';

import { getStoredUser } from '../services/authClient';
import {
  getLiveAnalytics,
  type AnalyticsSession,
  type LiveAnalyticsResponse,
} from '../services/analyticsClient';

const WINDOW_OPTIONS = [
  { label: 'Son 5 dk', value: 5 },
  { label: 'Son 30 dk', value: 30 },
  { label: 'Son 1 saat', value: 60 },
  { label: 'Son 24 saat', value: 1440 },
];

function roleLabel(role: string | null) {
  switch (role) {
    case 'admin':
      return 'Yönetici';
    case 'doctor':
      return 'Doktor';
    case 'lab_staff':
      return 'Laboratuvar';
    case 'patient':
      return 'Hasta';
    default:
      return 'Anonim';
  }
}

function locationLabel(session: AnalyticsSession): string {
  return [session.city, session.region, session.country].filter(Boolean).join(', ') || '—';
}

function coordinatesLabel(session: AnalyticsSession): string | null {
  if (session.latitude == null || session.longitude == null) return null;
  return `${session.latitude.toFixed(4)}, ${session.longitude.toFixed(4)}`;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(date);
}

function isOnline(lastSeen: string): boolean {
  const timestamp = new Date(lastSeen).getTime();
  return Number.isFinite(timestamp) && Date.now() - timestamp <= 90_000;
}

export default function AdminAnalyticsPage() {
  const user = getStoredUser();
  const [minutes, setMinutes] = useState(5);
  const [data, setData] = useState<LiveAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (user?.role !== 'admin') return;

    try {
      const response = await getLiveAnalytics(minutes, 200);
      setData(response);
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Canlı trafik alınamadı.');
    } finally {
      setLoading(false);
    }
  }, [minutes, user?.role]);

  useEffect(() => {
    setLoading(true);
    void load();

    const intervalId = window.setInterval(() => void load(), 15_000);
    return () => window.clearInterval(intervalId);
  }, [load]);

  const onlineCount = useMemo(
    () => data?.sessions.filter((session) => isOnline(session.last_seen_at)).length ?? 0,
    [data],
  );

  if (user?.role !== 'admin') {
    return (
      <section className="mx-auto max-w-3xl rounded-xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Yalnızca yönetici erişimi</h2>
        <p className="mt-2 text-sm text-amber-800">
          IP ve ziyaretçi trafiği kişisel veri içerdiği için bu ekran yalnızca yönetici hesabına açıktır.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">Yönetici</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">Canlı trafik</h2>
          <p className="mt-1 text-sm text-slate-500">
            Aktif ziyaretçiler, oturumlar, IP ve IP tabanlı yaklaşık konum bilgisi.
          </p>
        </div>

        <div className="flex items-end gap-2">
          <label className="text-sm font-medium text-slate-700">
            Zaman aralığı
            <select
              value={minutes}
              onChange={(event) => setMinutes(Number(event.target.value))}
              className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              {WINDOW_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800"
          >
            Yenile
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      {data && (!data.raw_ip_enabled || !data.geo_enabled) ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {!data.raw_ip_enabled ? (
            <p>
              <strong>Ham IP kaydı kapalı.</strong> Render ortamında{' '}
              <code>ANALYTICS_STORE_RAW_IP=true</code> ayarlanırsa yönetici ekranında IP görünür.
            </p>
          ) : null}
          {!data.geo_enabled ? (
            <p className={data.raw_ip_enabled ? '' : 'mt-2'}>
              <strong>IP konum çözümleme kapalı.</strong>{' '}
              <code>ANALYTICS_GEOLOOKUP_ENABLED=true</code> ile şehir/bölge/ülke ve yaklaşık koordinat eklenir.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-sm text-slate-500">Şu an çevrimiçi</p>
          <p className="mt-2 text-3xl font-semibold text-slate-950">{onlineCount}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-sm text-slate-500">Seçili aralık</p>
          <p className="mt-2 text-3xl font-semibold text-slate-950">{data?.total ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-sm text-slate-500">Giriş yapmış</p>
          <p className="mt-2 text-3xl font-semibold text-slate-950">{data?.authenticated ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-sm text-slate-500">Anonim</p>
          <p className="mt-2 text-3xl font-semibold text-slate-950">{data?.anonymous ?? 0}</p>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div>
            <h3 className="font-semibold text-slate-950">Ziyaretçi oturumları</h3>
            <p className="text-xs text-slate-500">15 saniyede bir otomatik yenilenir.</p>
          </div>
          {loading ? <span className="text-xs text-slate-500">Yükleniyor…</span> : null}
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Durum / kullanıcı</th>
                <th className="px-4 py-3">IP</th>
                <th className="px-4 py-3">Yaklaşık konum</th>
                <th className="px-4 py-3">Sayfa</th>
                <th className="px-4 py-3">Cihaz</th>
                <th className="px-4 py-3">Son görülme</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.sessions.map((session) => {
                const coords = coordinatesLabel(session);
                return (
                  <tr key={session.visitor_id} className="align-top">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className={`h-2.5 w-2.5 rounded-full ${
                            isOnline(session.last_seen_at) ? 'bg-emerald-500' : 'bg-slate-300'
                          }`}
                        />
                        <span className="font-medium text-slate-900">
                          {session.nickname ? `@${session.nickname}` : 'Anonim ziyaretçi'}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{roleLabel(session.role)}</p>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">
                      {session.ip_address ?? 'Gizli'}
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-slate-800">{locationLabel(session)}</p>
                      {coords ? <p className="mt-1 font-mono text-xs text-slate-500">{coords}</p> : null}
                      {session.timezone ? (
                        <p className="mt-1 text-xs text-slate-500">TZ: {session.timezone}</p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <p className="max-w-xs break-all font-mono text-xs text-slate-700">
                        {session.last_path ?? '—'}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">{session.request_count} heartbeat</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-slate-800">{session.platform ?? '—'}</p>
                      <p className="mt-1 text-xs text-slate-500">{session.language ?? '—'}</p>
                      <p
                        className="mt-1 max-w-xs truncate text-xs text-slate-400"
                        title={session.user_agent ?? undefined}
                      >
                        {session.user_agent ?? '—'}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">
                      {formatDate(session.last_seen_at)}
                    </td>
                  </tr>
                );
              })}

              {!loading && (data?.sessions.length ?? 0) === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-500">
                    Bu zaman aralığında ziyaretçi görünmüyor.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs leading-5 text-slate-500">
        Konum IP tabanlı yaklaşık bilgidir; GPS değildir ve şehir düzeyinde dahi hatalı olabilir. Ham IP ve
        konum verileri yalnızca yönetici endpoint'inden okunur.
      </p>
    </section>
  );
}
