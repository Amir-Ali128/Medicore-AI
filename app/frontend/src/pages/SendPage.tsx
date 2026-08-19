import { useEffect, useMemo, useState, type FormEvent } from 'react';

import SectionCard from '../components/ui/SectionCard';
import {
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400';

function reportDate(report: RadiologyReport) {
  return report.report_date || report.created_at.slice(0, 10);
}

function conciseSummary(report: RadiologyReport) {
  if (report.summary?.trim() && report.summary !== 'Rapor özeti oluşturulamadı.') {
    return report.summary.trim();
  }
  if (report.impression?.trim()) return report.impression.trim();
  return report.original_text.replace(/\s+/g, ' ').trim().slice(0, 1800);
}

export default function SendPage() {
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('MediCore radyoloji değerlendirme özeti');
  const [note, setNote] = useState('');
  const [includeRadiology, setIncludeRadiology] = useState(true);
  const [latestReport, setLatestReport] = useState<RadiologyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function loadLatestReport() {
      try {
        setLoading(true);
        const reports = await listPatientRadiologyReports();
        if (!cancelled) setLatestReport(reports[0] ?? null);
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Radyoloji raporu yüklenemedi.',
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadLatestReport();
    return () => {
      cancelled = true;
    };
  }, []);

  const emailBody = useMemo(() => {
    const parts: string[] = [];

    if (note.trim()) {
      parts.push(note.trim());
    }

    if (includeRadiology && latestReport) {
      parts.push(
        [
          '--- MediCore radyoloji değerlendirme özeti ---',
          `Tarih: ${reportDate(latestReport)}`,
          `Tetkik: ${latestReport.modality}`,
          `Bölge: ${latestReport.body_part}`,
          '',
          conciseSummary(latestReport),
        ].join('\n'),
      );
    }

    parts.push(
      'Not: Bu ileti kişisel sağlık verisi içerebilir. Alıcının doğru kişi olduğundan emin olun.',
    );

    return parts.join('\n\n');
  }, [includeRadiology, latestReport, note]);

  function openEmailClient(event: FormEvent) {
    event.preventDefault();
    setError('');

    const normalizedRecipient = recipient.trim();
    if (!normalizedRecipient || !normalizedRecipient.includes('@')) {
      setError('Geçerli bir alıcı e-posta adresi girin.');
      return;
    }

    const mailto = `mailto:${encodeURIComponent(normalizedRecipient)}?subject=${encodeURIComponent(
      subject.trim() || 'MediCore raporu',
    )}&body=${encodeURIComponent(emailBody)}`;

    window.location.href = mailto;
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">
          Güvenli paylaşım
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">E-posta ile gönder</h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
          MediCore, seçtiğin özeti cihazındaki e-posta uygulamasına hazırlar. E-posta otomatik
          gönderilmez; son alıcı ve içerik kontrolü sende kalır.
        </p>
      </header>

      <SectionCard
        title="Gönderim bilgileri"
        description="Alıcıyı doğrula, hangi içeriğin e-postaya ekleneceğini seç ve e-posta uygulamasını aç."
      >
        <form onSubmit={openEmailClient} className="space-y-5">
          <label className="block text-sm font-semibold text-slate-800">
            Alıcı e-posta adresi
            <input
              required
              type="email"
              value={recipient}
              onChange={(event) => setRecipient(event.target.value)}
              className={INPUT_CLASS}
              placeholder="doktor@kurum.com"
            />
          </label>

          <label className="block text-sm font-semibold text-slate-800">
            Konu
            <input
              type="text"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
              className={INPUT_CLASS}
            />
          </label>

          <label className="block text-sm font-semibold text-slate-800">
            Mesaj notu
            <textarea
              rows={5}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              className={`${INPUT_CLASS} resize-y`}
              placeholder="Kısa bir açıklama ekleyebilirsin..."
            />
          </label>

          <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <input
              type="checkbox"
              checked={includeRadiology}
              onChange={(event) => setIncludeRadiology(event.target.checked)}
              className="mt-1 h-4 w-4"
            />
            <span>
              <span className="block text-sm font-semibold text-slate-900">
                En güncel radyoloji özetini ekle
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-500">
                {loading
                  ? 'Rapor yükleniyor…'
                  : latestReport
                    ? `${reportDate(latestReport)} · ${latestReport.modality} · ${latestReport.body_part}`
                    : 'Bu hasta için gönderilecek radyoloji raporu bulunamadı.'}
              </span>
            </span>
          </label>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900">
            Sağlık verileri hassastır. Normal e-posta servisleri uçtan uca güvenli sağlık veri
            aktarımı için tasarlanmamış olabilir. Alıcı adresini ve kurum politikasını gönderimden
            önce kontrol edin.
          </div>

          {error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={includeRadiology && loading}
            className="rounded-lg bg-blue-700 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            E-posta uygulamasını aç
          </button>
        </form>
      </SectionCard>
    </div>
  );
}
