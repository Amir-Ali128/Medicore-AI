import { FormEvent, useEffect, useState } from 'react';

import { getStoredUser } from '../services/authClient';
import {
  getMyFeedback,
  submitFeedback,
  type FeedbackCategory,
  type FeedbackItem,
} from '../services/feedbackClient';

const CATEGORY_OPTIONS: Array<{ value: FeedbackCategory; label: string }> = [
  { value: 'suggestion', label: 'Öneri' },
  { value: 'bug', label: 'Hata bildirimi' },
  { value: 'usability', label: 'Kullanım kolaylığı' },
  { value: 'other', label: 'Diğer' },
];

function statusLabel(status: FeedbackItem['status']) {
  switch (status) {
    case 'new': return 'Yeni';
    case 'read': return 'Okundu';
    case 'resolved': return 'Çözüldü';
  }
}

function categoryLabel(category: FeedbackItem['category']) {
  return CATEGORY_OPTIONS.find((item) => item.value === category)?.label ?? category;
}

export default function UserFeedbackPage() {
  const user = getStoredUser();
  const [category, setCategory] = useState<FeedbackCategory>('suggestion');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (user?.role !== 'patient') {
      setLoading(false);
      return;
    }

    void getMyFeedback()
      .then(setItems)
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Geri bildirimler alınamadı.'))
      .finally(() => setLoading(false));
  }, [user?.role]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setSubmitting(true);
      setError('');
      setSuccess('');
      const created = await submitFeedback({ category, subject, message });
      setItems((current) => [created, ...current]);
      setSubject('');
      setMessage('');
      setCategory('suggestion');
      setSuccess('Mesajın yönetici gelen kutusuna gönderildi. Teşekkürler ✨');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Geri bildirim gönderilemedi.');
    } finally {
      setSubmitting(false);
    }
  }

  if (user?.role !== 'patient') {
    return (
      <section className="mx-auto max-w-2xl rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="text-lg font-semibold text-amber-950">Bireysel kullanıcı alanı</h2>
        <p className="mt-2 text-sm leading-6 text-amber-800">Bu form bireysel kullanıcı hesaplarından ürün önerisi ve geri bildirim almak için tasarlandı.</p>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-4xl space-y-5 pb-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-cyan-700">MediCore geri bildirim</p>
        <h2 className="mt-1 text-2xl font-semibold text-slate-950">Öneri veya hata bildir</h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">Gönderdiğin mesaj yalnızca yönetici panelindeki geri bildirim gelen kutusunda görüntülenir.</p>
      </div>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">
        Lütfen hasta adı, TC kimlik numarası, protokol numarası, tahlil sonucu veya başka sağlık verisi yazma. Bu alan ürün önerisi ve teknik geri bildirim içindir.
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Tür</span>
          <select value={category} onChange={(event) => setCategory(event.target.value as FeedbackCategory)} className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-100">
            {CATEGORY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Konu</span>
          <input value={subject} onChange={(event) => setSubject(event.target.value)} required minLength={3} maxLength={120} className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-100" placeholder="Örn. PDF yükleme ekranı için öneri" />
        </label>

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Mesaj</span>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} required minLength={10} maxLength={2000} rows={6} className="mt-2 w-full resize-y rounded-xl border border-slate-200 px-4 py-3 text-sm leading-6 outline-none focus:border-blue-400 focus:ring-4 focus:ring-blue-100" placeholder="Ne değişse daha iyi olurdu? Bir hata gördüysen nasıl oluştuğunu anlatabilirsin." />
          <span className="mt-1 block text-right text-xs text-slate-400">{message.length}/2000</span>
        </label>

        {success ? <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{success}</div> : null}
        {error ? <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div> : null}

        <button type="submit" disabled={submitting} className="w-full rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-60 sm:w-auto sm:px-6">
          {submitting ? 'Gönderiliyor…' : 'Yöneticiye gönder'}
        </button>
      </form>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-slate-950">Gönderdiklerim</h3>
            <p className="mt-1 text-xs text-slate-500">Yönetici okuduğunda veya çözüldü olarak işaretlediğinde durum burada değişir.</p>
          </div>
          {loading ? <span className="text-xs text-slate-400">Yükleniyor…</span> : null}
        </div>

        <div className="mt-4 space-y-3">
          {items.map((item) => (
            <article key={item.id} className="rounded-xl border border-slate-200 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium text-slate-900">{item.subject}</p>
                <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">{statusLabel(item.status)}</span>
              </div>
              <p className="mt-1 text-xs font-medium text-cyan-700">{categoryLabel(item.category)}</p>
              <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-600">{item.message}</p>
            </article>
          ))}
          {!loading && items.length === 0 ? <p className="py-4 text-sm text-slate-500">Henüz geri bildirim göndermedin.</p> : null}
        </div>
      </div>
    </section>
  );
}
