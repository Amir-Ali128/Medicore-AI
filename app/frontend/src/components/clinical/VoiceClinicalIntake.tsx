import { useEffect, useMemo, useRef, useState } from 'react';
import { ClinicalVoiceSession, type VoiceStatus } from '../../services/clinicalVoiceClient';
import { approvedVoicePatch, extractVoiceDraft, isVoiceTextField, validateVoiceValue, VOICE_LABELS, type VoiceChoice, type VoiceField, type VoiceForm } from '../../services/voiceClinicalDraft';
import { capturePatientScope, isCurrentPatientScope } from '../../services/patientScope';

type Props = { values: VoiceForm; onApply: (patch: Partial<VoiceForm>) => void };
type Selection = VoiceChoice & { selected: boolean };
const SEX_LABELS: Record<string, string> = { male: 'Erkek', female: 'Kadın', other: 'Diğer', unknown: 'Belirtilmedi' };
const sexLabel = (value: string) => SEX_LABELS[value] ?? value;

export default function VoiceClinicalIntake({ values, onApply }: Props) {
  const [transcript, setTranscript] = useState('');
  const [status, setStatus] = useState<VoiceStatus>('idle');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [lowConfidence, setLowConfidence] = useState(false);
  const [choices, setChoices] = useState<Partial<Record<VoiceField, Selection>>>({});
  const [approvedText, setApprovedText] = useState<string | null>(null);
  const [renewal, setRenewal] = useState(0);
  const [base, setBase] = useState<VoiceForm>({ ...values });
  const current = useRef(values); current.current = values;
  const scope = useRef(capturePatientScope());
  const session = useRef<ClinicalVoiceSession | null>(null);
  const mounted = useRef(true);
  const busy = status !== 'idle';
  const parsed = useMemo(() => {
    try { return { ...extractVoiceDraft(transcript), error: '' }; }
    catch (failure) { return { candidates: [], unmapped: [], error: failure instanceof Error ? failure.message : 'Metin ayrıştırılamadı.' }; }
  }, [transcript]);

  useEffect(() => {
    setBase({ ...current.current }); scope.current = capturePatientScope();
    setChoices({}); setApprovedText(null); setMessage('');
  }, [transcript, renewal]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; session.current?.cancel(); };
  }, []);

  function start() {
    session.current?.cancel(); setError(''); setMessage(''); setApprovedText(null);
    const next = new ClinicalVoiceSession({
      onStatus: (nextStatus) => { if (mounted.current) setStatus(nextStatus); },
      onText: (text, review) => {
        if (!mounted.current) return;
        setTranscript((previous) => `${previous}${previous ? ' ' : ''}${text}`);
        if (review) setLowConfidence(true);
      },
      onError: (text) => { if (mounted.current) setError(text); },
    });
    session.current = next; void next.start();
  }

  function choose(field: VoiceField, change: Partial<Selection>) {
    const candidate = parsed.candidates.find((item) => item.field === field)!;
    setChoices((previous) => ({ ...previous, [field]: {
      field, value: candidate.value, mode: isVoiceTextField(field) ? 'append' : 'replace', overwrite: false, reviewed: false, selected: false,
      ...previous[field], ...change,
    } }));
    setApprovedText(null); setMessage('');
  }

  function apply() {
    setError('');
    try {
      if (busy || !isCurrentPatientScope(scope.current)) throw new Error('Vaka değişti veya ses işlemi sürüyor; taslağı yeniden inceleyin.');
      const selected = Object.values(choices).filter((choice): choice is Selection => Boolean(choice?.selected));
      const patch = approvedVoicePatch(base, current.current, parsed.candidates, selected, approvedText === transcript);
      onApply(patch);
      setChoices({}); setApprovedText(null);
      setMessage('Seçili alanlar forma taslak olarak aktarıldı. Kalıcı kayıt için mevcut vaka kaydetme düğmesini kullanın.');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Taslak forma aktarılamadı.'); }
  }

  return <section aria-label="Sesli klinik giriş" className="mb-6 rounded-2xl border border-blue-200 bg-blue-50/40 p-4 sm:p-5">
    <h2 className="text-lg font-semibold text-slate-950">Sesli klinik giriş · Türkçe</h2>
    <p className="mt-1 text-sm text-slate-600">Ses yalnızca MediCore sunucusunda işlenir. Alanları inceleyip onaylamadan form veya hasta kaydı değiştirilmez.</p>
    <div className="mt-3 flex flex-wrap items-center gap-3">
      <button type="button" onClick={start} disabled={busy} className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">Konuşmaya başla</button>
      <button type="button" onClick={() => session.current?.stop()} disabled={!busy || status === 'stopping'} className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm disabled:opacity-40">Durdur</button>
      <span role="status" className="text-sm text-slate-600">{status === 'preparing' ? 'Mikrofon hazırlanıyor…' : status === 'listening' ? 'Dinleniyor · Metin parçalar halinde güncellenir' : status === 'stopping' ? 'Son ses parçası okunuyor…' : 'Kayıt kapalı'}</span>
    </div>
    <p className="mt-2 text-xs text-slate-500">En fazla 3 dakika. Cümle sonunda kısa duraklayın; sayıları ve birimleri açık söyleyin. Mikrofon kullanılamıyorsa metni aşağıya yazabilirsiniz. Fizik muayene, Ek klinik not alanına eşlenir. Sesli giriş taslaktır; özellikle sayıları ve tıbbi terimleri kontrol edin.</p>
    <label className="mt-4 block text-sm font-medium text-slate-700">Canlı transkripsiyon
      <textarea value={transcript} disabled={busy} maxLength={12000} onChange={(event) => { setTranscript(event.target.value); setApprovedText(null); }} rows={4}
        placeholder="Örnek: Altmış beş yaşında erkek. Şikayetler: iki gündür kusma. Anamnez: hipertansiyon. Vital bulgular: tansiyon 145/90, nabız 108, ateş 37,2. Muayenede ağız mukozası kuru."
        className="mt-1 block w-full rounded-xl border border-slate-300 bg-white px-3 py-2 font-normal disabled:opacity-70" />
    </label>
    {lowConfidence ? <p className="mt-2 text-sm text-amber-800">Bazı ses parçalarında tanıma güveni düşüktü. Transkripsiyonu dinlediğiniz bilgiyle karşılaştırıp düzeltin.</p> : null}
    {error || parsed.error ? <p role="alert" className="mt-3 text-sm text-red-700">{error || parsed.error}</p> : null}
    {parsed.candidates.length ? <fieldset disabled={busy} className="mt-4 space-y-3">
      <legend className="font-semibold text-slate-800">Alan taslakları · Hiçbir alan kendiliğinden uygulanmaz</legend>
      {parsed.candidates.map((candidate) => {
        const field = candidate.field;
        const choice = choices[field];
        const value = choice?.value ?? candidate.value;
        const existing = values[field]?.trim() && !(field === 'sex' && values[field] === 'unknown');
        const validation = validateVoiceValue(field, value);
        return <div key={field} className="rounded-xl border border-slate-200 bg-white p-3">
          <label className="flex items-center gap-2 text-sm font-semibold"><input type="checkbox" checked={choice?.selected ?? false} onChange={(event) => choose(field, { selected: event.target.checked })} />{VOICE_LABELS[field]}</label>
          {existing ? <p className="mt-2 whitespace-pre-line text-xs text-slate-600">Mevcut değer: {field === 'sex' ? sexLabel(values[field]) : values[field]}</p> : null}
          {base[field] !== values[field] ? <p className="mt-1 text-xs text-amber-800">Form alanı bu sırada değişti. Taslağı yenileyin.</p> : null}
          {field === 'sex' ? <select aria-label="Cinsiyet taslağı" value={value} onChange={(event) => choose(field, { value: event.target.value })} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm">
            <option value="">Seçin</option><option value="male">Erkek</option><option value="female">Kadın</option><option value="other">Diğer</option>
          </select> : isVoiceTextField(field) ? <textarea aria-label={`${VOICE_LABELS[field]} taslağı`} rows={2} value={value} onChange={(event) => choose(field, { value: event.target.value })} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            : <input aria-label={`${VOICE_LABELS[field]} taslağı`} type="text" inputMode="decimal" value={value} onChange={(event) => choose(field, { value: event.target.value })} className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />}
          {validation ? <p className="mt-1 text-xs text-amber-800">{validation}</p> : null}
          <p className="mt-2 whitespace-pre-line text-xs text-slate-500">Kaynak: {candidate.source.join('\n')}</p>
          {candidate.alternatives.length > 1 && !isVoiceTextField(field) ? <p className="mt-1 text-xs text-amber-800">Söylenen değerler: {candidate.alternatives.map((value) => field === 'sex' ? sexLabel(value) : value).join(' / ')}</p> : null}
          {candidate.issues.length ? <div className="mt-2 text-xs text-amber-800"><p>{candidate.issues.join(' ')}</p><label className="mt-1 flex items-center gap-2"><input type="checkbox" checked={choice?.reviewed ?? false} onChange={(event) => choose(field, { reviewed: event.target.checked })} />Bu alanın belirsizliğini kontrol ettim</label></div> : null}
          {existing && isVoiceTextField(field) ? <label className="mt-2 block text-xs text-slate-600">Aktarma biçimi<select aria-label={`${VOICE_LABELS[field]} aktarma biçimi`} value={choice?.mode ?? 'append'} onChange={(event) => choose(field, { mode: event.target.value as 'append' | 'replace' })} className="ml-2 rounded border border-slate-300 p-1"><option value="append">Mevcut metne ekle</option><option value="replace">Mevcut metni değiştir</option></select></label> : null}
          {existing && (!isVoiceTextField(field) || choice?.mode === 'replace') ? <label className="mt-2 flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={choice?.overwrite ?? false} onChange={(event) => choose(field, { overwrite: event.target.checked })} />Mevcut değeri değiştirmeyi onaylıyorum</label> : null}
        </div>;
      })}
      <label className="flex items-start gap-2 text-sm text-slate-700"><input type="checkbox" checked={approvedText === transcript} onChange={(event) => setApprovedText(event.target.checked ? transcript : null)} />Taslağı gözden geçirdim; seçtiğim alanların forma aktarılmasını onaylıyorum.</label>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={apply} disabled={approvedText !== transcript || !Object.values(choices).some((choice) => choice?.selected)} className="rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white disabled:opacity-40">Seçili alanları forma aktar</button>
        <button type="button" onClick={() => setRenewal((value) => value + 1)} className="rounded-xl border border-slate-300 px-4 py-2 text-sm">Güncel formdan taslağı yenile</button>
      </div>
    </fieldset> : null}
    {parsed.unmapped.length ? <details className="mt-3 text-sm text-amber-800"><summary>Eşleştirilemeyen ifadeler ({parsed.unmapped.length})</summary><p className="mt-1 whitespace-pre-line">{parsed.unmapped.join('\n')}</p></details> : null}
    {message ? <p role="status" className="mt-3 text-sm text-blue-800">{message}</p> : null}
  </section>;
}
