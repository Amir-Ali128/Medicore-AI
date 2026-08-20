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
    case 'admin': return 'Yönetici';
    case 'doctor': return 'Doktor';
    case 'lab_staff': return 'Laboratuvar';
    case 'patient': return 'Hasta';
    default: return 'Anonim';
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
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'medium' }).format(date);
}

function relativeLastSeen(value: string): string {
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms) || ms < 0) return formatDate(value);
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds} sn önce`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} dk önce`;
  return formatDate(value);
}

function isOnline(lastSeen: string): boolean {
  const timestamp = new Date(lastSeen).getTime();
  return Number.isFinite(timestamp) && Date.now() - timestamp <= 90_000;
}

function deviceTypeLabel(type: string | null): string | null {
  switch (type) {
    case 'mobile': return 'Mobil';
    case 'tablet': return 'Tablet';
    case 'desktop': return 'Masaüstü';
    default: return type;
  }
}

function joinVersion(name: string | null, version: string | null): string | null {
  const value = [name, version].filter(Boolean).join(' ');
  return value || null;
}

function deviceTitle(session: AnalyticsSession): string {
  const model = [session.device_brand, session.device_model].filter(Boolean).join(' ');
  return model || session.platform || 'Model bilinmiyor';
}

function modelSourceLabel(source: string | null): string | null {
  switch (source) {
    case 'client-hints-reported': return 'Tarayıcı bildirdi';
    case 'user-agent-reported': return 'User-Agent bildirdi';
    case 'screen-profile-inferred': return 'Ekran profilinden tahmin';
    case 'screen-profile-unmatched': return 'Ekran profili eşleşmedi';
    case 'generic': return 'Genel cihaz ailesi';
    default: return source;
  }
}

function confidenceLabel(confidence: AnalyticsSession['device_model_confidence']): string | null {
  switch (confidence) {
    case 'high': return 'Yüksek güven';
    case 'medium': return 'Orta güven';
    case 'low': return 'Düşük güven';
    default: return null;
  }
}

function SessionMobileCard({ session }: { session: AnalyticsSession }) {
  const os = joinVersion(session.os_name, session.os_version);
  const browser = joinVersion(session.browser_name, session.browser_version);
  const source = modelSourceLabel(session.device_model_source);
  const confidence = confidenceLabel(session.device_model_confidence);
  const coords = coordinatesLabel(session);

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${isOnline(session.last_seen_at) ? 'bg-emerald-500' : 'bg-slate-300'}`} />
            <p className="truncate font-semibold text-slate-950">
              {session.nickname ? `@${session.nickname}` : 'Anonim ziyaretçi'}
            </p>
          </div>
          <p className="mt-1 text-xs text-slate-500">{roleLabel(session.role)}</p>
        </div>
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600">
          {relativeLastSeen(session.last_seen_at)}
        </span>
      </div>

      <div className="mt-4 rounded-2xl bg-slate-50 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cihaz</p>
        <p className="mt-1 font-semibold text-slate-900">{deviceTitle(session)}</p>
        {(source || confidence) ? (
          <p className="mt-1 text-xs font-medium text-cyan-700">{[source, confidence].filter(Boolean).join(' · ')}</p>
        ) : null}
        <p className="mt-1 text-xs text-slate-600">
          {[deviceTypeLabel(session.device_type), os, browser].filter(Boolean).join(' · ') || '—'}
        </p>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-slate-400">IP</p>
          <p className="mt-1 break-all font-mono text-slate-700">{session.ip_address ?? 'Gizli'}</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-3">
          <p className="text-slate-400">Konum</p>
          <p className="mt-1 text-slate-700">{locationLabel(session)}</p>
          {coords ? <p className="mt-1 font-mono text-[10px] text-slate-400">{coords}</p> : null}
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-slate-200 p-3 text-xs">
        <p className="text-slate-400">Son sayfa</p>
        <p className="mt-1 break-all font-mono text-slate-700">{session.last_path ?? '—'}</p>
        <p className="mt-1 text-slate-400">{session.request_count} heartbeat</p>
      </div>
    </article>
  );
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
        <p className="mt-2 text-sm text-amber-800">IP, yaklaşık konum ve cihaz bilgileri kişisel veri içerebildiği için bu ekran yalnızca yönetici hesabına açıktır.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">Yönetici</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">Canlı trafik</h2>
          <p className="mt-1 text-sm text-slate-500">Aktif ziyaretçiler, IP, yaklaşık konum ve cihaz bilgileri.</p>
        </div>

        <div className="grid grid-cols-[1fr_auto] gap-2 sm:flex sm:items-end">
          <label className="text-sm font-medium text-slate-700">
            Zaman aralığı
            <select value={minutes} onChange={(event) => setMinutes(Number(event.target.value))} className="mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm">
              {WINDOW_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <button type="button" onClick={() => void load()} className="self-end rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-800">Yenile</button>
        </div>
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div> : null}

      {data && (!data.raw_ip_enabled || !data.geo_enabled) ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          {!data.raw_ip_enabled ? <p><strong>Ham IP kaydı kapalı.</strong> <code>ANALYTICS_STORE_RAW_IP=true</code></p> : null}
          {!data.geo_enabled ? <p className={data.raw_ip_enabled ? '' : 'mt-2'}><strong>IP konum çözümleme kapalı.</strong> <code>ANALYTICS_GEOLOOKUP_ENABLED=true</code></p> : null}
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
        {[
          ['Şu an çevrimiçi', onlineCount],
          ['Seçili aralık', data?.total ?? 0],
          ['Giriş yapmış', data?.authenticated ?? 0],
          ['Anonim', data?.anonymous ?? 0],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-5">
            <p className="text-xs text-slate-500 sm:text-sm">{label}</p>
            <p className="mt-1 text-2xl font-semibold text-slate-950 sm:mt-2 sm:text-3xl">{value}</p>
          </div>
        ))}
      </div>

      <div className="md:hidden">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-slate-950">Ziyaretçi oturumları</h3>
            <p className="text-xs text-slate-500">15 saniyede bir yenilenir.</p>
          </div>
          {loading ? <span className="text-xs text-slate-400">Yükleniyor…</span> : null}
        </div>
        <div className="space-y-3">
          {data?.sessions.map((session) => <SessionMobileCard key={session.visitor_id} session={session} />)}
          {!loading && (data?.sessions.length ?? 0) === 0 ? <div className="rounded-2xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">Bu zaman aralığında ziyaretçi görünmüyor.</div> : null}
        </div>
      </div>

      <div className="hidden overflow-hidden rounded-xl border border-slate-200 bg-white md:block">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <div><h3 className="font-semibold text-slate-950">Ziyaretçi oturumları</h3><p className="text-xs text-slate-500">15 saniyede bir otomatik yenilenir.</p></div>
          {loading ? <span className="text-xs text-slate-500">Yükleniyor…</span> : null}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-3">Durum / kullanıcı</th><th className="px-4 py-3">IP</th><th className="px-4 py-3">Yaklaşık konum</th><th className="px-4 py-3">Sayfa</th><th className="px-4 py-3">Cihaz / tarayıcı</th><th className="px-4 py-3">Son görülme</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.sessions.map((session) => {
                const coords = coordinatesLabel(session);
                const os = joinVersion(session.os_name, session.os_version);
                const browser = joinVersion(session.browser_name, session.browser_version);
                const source = modelSourceLabel(session.device_model_source);
                const confidence = confidenceLabel(session.device_model_confidence);
                return (
                  <tr key={session.visitor_id} className="align-top">
                    <td className="px-4 py-3"><div className="flex items-center gap-2"><span className={`h-2.5 w-2.5 rounded-full ${isOnline(session.last_seen_at) ? 'bg-emerald-500' : 'bg-slate-300'}`} /><span className="font-medium text-slate-900">{session.nickname ? `@${session.nickname}` : 'Anonim ziyaretçi'}</span></div><p className="mt-1 text-xs text-slate-500">{roleLabel(session.role)}</p></td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700">{session.ip_address ?? 'Gizli'}</td>
                    <td className="px-4 py-3"><p className="text-slate-800">{locationLabel(session)}</p>{coords ? <p className="mt-1 font-mono text-xs text-slate-500">{coords}</p> : null}</td>
                    <td className="px-4 py-3"><p className="max-w-xs break-all font-mono text-xs text-slate-700">{session.last_path ?? '—'}</p><p className="mt-1 text-xs text-slate-500">{session.request_count} heartbeat</p></td>
                    <td className="px-4 py-3"><p className="font-medium text-slate-900">{deviceTitle(session)}</p>{(source || confidence) ? <p className="mt-1 text-xs font-medium text-cyan-700">{[source, confidence].filter(Boolean).join(' · ')}</p> : null}<p className="mt-1 text-xs text-slate-600">{[deviceTypeLabel(session.device_type), os].filter(Boolean).join(' · ') || session.platform || '—'}</p>{browser ? <p className="mt-1 text-xs text-slate-600">{browser}</p> : null}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">{formatDate(session.last_seen_at)}</td>
                  </tr>
                );
              })}
              {!loading && (data?.sessions.length ?? 0) === 0 ? <tr><td colSpan={6} className="px-4 py-10 text-center text-sm text-slate-500">Bu zaman aralığında ziyaretçi görünmüyor.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-xs leading-5 text-slate-500">iPhone model adı Safari tarafından doğrudan verilmediğinde ekran profili yalnızca aday model grubu üretmek için kullanılır. Konum IP tabanlı yaklaşık bilgidir; GPS değildir.</p>
    </section>
  );
}
