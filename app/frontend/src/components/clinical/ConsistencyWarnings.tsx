import type { ConsistencyFlag } from '../../services/simpleCaseClient';

export default function ConsistencyWarnings({ flags }: { flags: ConsistencyFlag[] }) {
  const unique = [...new Map(flags.map((flag) => [JSON.stringify(flag), flag])).values()];
  return <section aria-label="Veri tutarlılık uyarıları" className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
    <h3 className="font-semibold">Veri tutarlılık uyarıları</h3>
    {!unique.length ? <p className="mt-2">Tespit edilen veri tutarsızlığı yok.</p> : <ul className="mt-2 space-y-2">
      {unique.map((flag, index) => <li key={index} className="rounded-lg border border-amber-200 bg-white/70 p-2">
        <strong>{flag.parameter_or_report}</strong> · {flag.date || 'Tarih belirtilmedi'} · Sayfa {flag.source_page ?? 'belirtilmedi'} · Satır {flag.source_row ?? 'belirtilmedi'}
        {flag.severity === 'high' ? <span className="ml-2 font-semibold text-red-700">Yüksek öncelikli veri kontrolü</span> : null}
        <p>{flag.message_tr}</p>
      </li>)}
    </ul>}
  </section>;
}
