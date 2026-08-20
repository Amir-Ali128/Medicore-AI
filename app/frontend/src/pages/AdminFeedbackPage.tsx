import { useCallback, useEffect, useMemo, useState } from 'react';

import { getStoredUser } from '../services/authClient';
import {
  getAdminFeedback,
  setFeedbackStatus,
  type FeedbackItem,
  type FeedbackStatus,
} from '../services/feedbackClient';

function categoryLabel(category: FeedbackItem['category']) {
  switch (category) {
    case 'suggestion': return 'Öneri';
    case 'bug': return 'Hata';
    case 'usability': return 'Kullanım kolaylığı';
    case 'other': return 'Diğer';
  }
}

function statusLabel(status: FeedbackStatus) {
  switch (status) {
    case 'new': return 'Yeni';
    case 'read': return 'Okundu';
    case 'resolved': return 'Çözüldü';
  }
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
}

export default function AdminFeedbackPage() {
  const user = getStoredUser();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState<'all' | FeedbackStatus>('all');

  const load = useCallback(async () => {
    if (user?.role !== 'admin') return;
    try {
      setLoading(true);
      setItems(await getAdminFeedback());
      setError('');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Geri bildirimler alınamadı.');
    } finally {
      setLoading(false);
    }
  }, [user?.role]);

  useEffect(() => {
    void load();
  }, [load]);

  const visibleItems = useMemo(
    () => filter === 'all' ? items : items.filter((item) => item.status === filter),
    [filter, items],
  );
  const newCount = useMemo(() => items.filter((item) => item.status === 'new').length, [items]);

  async function changeStatus(item: FeedbackItem, status: FeedbackStatus) {
    try {
      const updated = await setFeedbackStatus(item.id, status);
      setItems((current) => current.map((entry) => entry.id === updated.id ? updated : entry));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Durum güncellenemedi.');
    }
  }

  if (user?.role !== 'admin') {
    return (
      <section className="mx-auto max-w-2xl rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Yalnızca yönetici erişimi</h2>
        <p className="mt-2 text-sm text-amber-800">Kullanıcı geri bildirimleri yalnızca yönetici hesabıyla görüntülenebilir.</p>
      </section>
    );
  }

  return (
    <section className="space-y-4 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">Yönetici</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-950">Geri bildirim gelen kutusu</h2>
          <p className="mt-1 text-sm text-slate-500">Bireysel kullanıcıların ürün önerileri, hata bildirimleri ve kullanım yorumları.</p>
        </div>
        <button type="button" onClick={() => void load()} className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white sm:self-auto">
          Yenile
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">Toplam</p><p className="mt-1 text-2xl font-semibold">{items.length}</p></div>
        <div className="rounded-2xl border border-cyan-200 bg-cyan-50 p-4"><p className="text-xs text-cyan-700">Yeni</p><p className="mt-1 text-2xl font-semibold text-cyan-950">{newCount}</p></div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">Okundu</p><p className="mt-1 text-2xl font-semibold">{items.filter((item) => item.status === 'read').length}</p></div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4"><p className="text-xs text-slate-500">Çözüldü</p><p className="mt-1 text-2xl font-semibold">{items.filter((item) => item.status === 'resolved').length}</p></div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {([
          ['all', 'Tümü'],
          ['new', 'Yeni'],
          ['read', 'Okundu'],
          ['resolved', 'Çözüldü'],
        ] as const).map(([value, label]) => (
          <button key={value} type="button" onClick={() => setFilter(value)} className={`shrink-0 rounded-full px-4 py-2 text-sm font-semibold ${filter === value ? 'bg-slate-950 text-white' : 'bg-white text-slate-600 ring-1 ring-slate-200'}`}>
            {label}
          </button>
        ))}
      </div>

      {error ? <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div> : null}

      <div className="space-y-3">
        {visibleItems.map((item) => (
          <article key={item.id} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-semibold text-cyan-700">{categoryLabel(item.category)}</span>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{statusLabel(item.status)}</span>
                </div>
                <h3 className="mt-3 text-lg font-semibold text-slate-950">{item.subject}</h3>
                <p className="mt-1 text-xs text-slate-500">@{item.nickname ?? 'silinmiş-kullanıcı'} · {formatDate(item.created_at)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {item.status !== 'read' ? <button type="button" onClick={() => void changeStatus(item, 'read')} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700">Okundu</button> : null}
                {item.status !== 'resolved' ? <button type="button" onClick={() => void changeStatus(item, 'resolved')} className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white">Çözüldü</button> : null}
                {item.status !== 'new' ? <button type="button" onClick={() => void changeStatus(item, 'new')} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600">Yeniye al</button> : null}
              </div>
            </div>
            <p className="mt-4 whitespace-pre-wrap rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-700">{item.message}</p>
          </article>
        ))}

        {!loading && visibleItems.length === 0 ? <div className="rounded-2xl border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">Bu filtrede geri bildirim yok.</div> : null}
        {loading ? <div className="rounded-2xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-500">Yükleniyor…</div> : null}
      </div>
    </section>
  );
}
