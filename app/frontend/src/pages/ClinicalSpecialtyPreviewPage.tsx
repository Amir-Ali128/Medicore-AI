import SectionCard from '../components/ui/SectionCard';

export type ClinicalSpecialty =
  | 'internal-medicine'
  | 'pulmonology'
  | 'neurology'
  | 'hematology'
  | 'infectious-diseases'
  | 'nephrology'
  | 'gastroenterology'
  | 'endocrinology'
  | 'oncology'
  | 'rheumatology'
  | 'pediatrics'
  | 'obstetrics-gynecology'
  | 'emergency-medicine';

type SpecialtyConfig = {
  title: string;
  eyebrow: string;
  phase: string;
  description: string;
  workspaceTitle: string;
  summaryTitle: string;
  plannedFeatures: string[];
  dataSources: string[];
  disclaimer: string;
};

const SPECIALTIES: Record<ClinicalSpecialty, SpecialtyConfig> = {
  'internal-medicine': {
    title: 'İç Hastalıkları',
    eyebrow: 'Dahili Klinik Karar Desteği',
    phase: 'Faz 5',
    description: 'Çoklu sistem bulgularını, laboratuvar sonuçlarını, ilaçları ve klinik notları birlikte değerlendirmek için planlanan dahiliye çalışma alanı.',
    workspaceTitle: 'İç hastalıkları çalışma alanı',
    summaryTitle: 'AI Dahiliye Özeti',
    plannedFeatures: ['Problem listesi oluşturma', 'Çoklu hastalık ve ilaç etkileşimi görünümü', 'Laboratuvar trendlerinin klinik bağlamda değerlendirilmesi', 'Konsültasyon gereksinimi için karar desteği', 'Takip planı ve eksik veri uyarıları'],
    dataSources: ['Laboratuvar', 'Klinik notlar', 'İlaçlar', 'Vital bulgular', 'Görüntüleme raporları'],
    disclaimer: 'Bu modül iç hastalıkları uzmanı değerlendirmesinin yerine geçmez.',
  },
  pulmonology: {
    title: 'Göğüs Hastalıkları',
    eyebrow: 'Solunum Sistemi Karar Desteği',
    phase: 'Faz 6',
    description: 'Solunum fonksiyonları, kan gazı, toraks görüntüleme ve klinik bulguları birlikte incelemek için planlanan çalışma alanı.',
    workspaceTitle: 'Göğüs hastalıkları çalışma alanı',
    summaryTitle: 'AI Solunum Özeti',
    plannedFeatures: ['SFT sonuçlarının yapılandırılması', 'Arter kan gazı değerlendirmesi', 'Astım ve KOAH takip görünümü', 'Toraks görüntüleme bulgularıyla eşleştirme', 'Oksijenasyon ve solunum trendleri'],
    dataSources: ['SFT', 'Kan gazı', 'SpO₂', 'Toraks BT', 'Akciğer grafisi', 'CRP / Prokalsitonin'],
    disclaimer: 'Bu modül göğüs hastalıkları uzmanı değerlendirmesinin yerine geçmez.',
  },
  neurology: {
    title: 'Nöroloji',
    eyebrow: 'Nörolojik Klinik Karar Desteği',
    phase: 'Faz 6.5',
    description: 'Nörolojik muayene, beyin görüntüleme, EEG ve klinik zaman çizelgesini birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Nöroloji çalışma alanı',
    summaryTitle: 'AI Nöroloji Özeti',
    plannedFeatures: ['Nörolojik bulguların yapılandırılması', 'İnme açısından zaman kritik uyarılar', 'Beyin BT ve MR raporlarının eşleştirilmesi', 'EEG özetleme ve olay işaretleme', 'Semptom ve tedavi yanıtı zaman çizelgesi'],
    dataSources: ['Nörolojik muayene', 'Beyin BT', 'Beyin MR', 'EEG', 'EMG', 'Klinik notlar'],
    disclaimer: 'Bu modül nöroloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  hematology: {
    title: 'Hematoloji',
    eyebrow: 'Hematolojik Karar Desteği',
    phase: 'Faz 7',
    description: 'Tam kan sayımı, koagülasyon, demir metabolizması ve kemik iliği verilerini birlikte incelemek için planlanan modül.',
    workspaceTitle: 'Hematoloji çalışma alanı',
    summaryTitle: 'AI Hematoloji Özeti',
    plannedFeatures: ['Anemi paternlerinin sınıflandırılması', 'Sitopeni ve sitoz trendleri', 'Koagülasyon bozukluğu uyarıları', 'Periferik yayma ve kemik iliği raporu entegrasyonu', 'Transfüzyon ve takip görünümü'],
    dataSources: ['Hemogram', 'Ferritin', 'B12 / Folat', 'PT / aPTT / INR', 'Periferik yayma', 'Kemik iliği raporu'],
    disclaimer: 'Bu modül hematoloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  'infectious-diseases': {
    title: 'Enfeksiyon Hastalıkları',
    eyebrow: 'Enfeksiyon Klinik Karar Desteği',
    phase: 'Faz 7.5',
    description: 'Kültür, antibiyogram, inflamasyon belirteçleri ve klinik bulguları tek çalışma alanında değerlendirmek için planlanan modül.',
    workspaceTitle: 'Enfeksiyon hastalıkları çalışma alanı',
    summaryTitle: 'AI Enfeksiyon Özeti',
    plannedFeatures: ['Olası enfeksiyon odağı görünümü', 'Kültür ve antibiyogram eşleştirmesi', 'Direnç paterni uyarıları', 'Antimikrobiyal tedavi zaman çizelgesi', 'Sepsis açısından erken uyarı desteği'],
    dataSources: ['Kültür', 'Antibiyogram', 'PCR', 'CRP', 'Prokalsitonin', 'Vital bulgular'],
    disclaimer: 'Bu modül enfeksiyon hastalıkları uzmanı değerlendirmesinin yerine geçmez.',
  },
  nephrology: {
    title: 'Nefroloji',
    eyebrow: 'Böbrek Sağlığı Karar Desteği',
    phase: 'Faz 8',
    description: 'Böbrek fonksiyonları, elektrolitler, idrar analizi ve sıvı dengesini birlikte izlemek için planlanan modül.',
    workspaceTitle: 'Nefroloji çalışma alanı',
    summaryTitle: 'AI Nefroloji Özeti',
    plannedFeatures: ['eGFR ve kreatinin trendleri', 'Akut böbrek hasarı uyarıları', 'Elektrolit bozukluklarının sınıflandırılması', 'İdrar ve proteinüri değerlendirmesi', 'Diyaliz ve sıvı dengesi görünümü'],
    dataSources: ['Kreatinin', 'eGFR', 'Üre', 'Elektrolitler', 'Tam idrar', 'Proteinüri'],
    disclaimer: 'Bu modül nefroloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  gastroenterology: {
    title: 'Gastroenteroloji',
    eyebrow: 'Sindirim Sistemi Karar Desteği',
    phase: 'Faz 8.5',
    description: 'Karaciğer testleri, endoskopi, abdominal görüntüleme ve klinik öyküyü birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Gastroenteroloji çalışma alanı',
    summaryTitle: 'AI Gastroenteroloji Özeti',
    plannedFeatures: ['Karaciğer fonksiyon paternleri', 'Endoskopi raporu yapılandırması', 'Abdominal görüntüleme eşleştirmesi', 'GİS kanama ve inflamasyon uyarıları', 'Tedavi ve takip zaman çizelgesi'],
    dataSources: ['AST / ALT', 'Bilirubin', 'Amilaz / Lipaz', 'Endoskopi', 'Abdominal USG', 'Abdominal BT / MR'],
    disclaimer: 'Bu modül gastroenteroloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  endocrinology: {
    title: 'Endokrinoloji',
    eyebrow: 'Endokrin ve Metabolik Karar Desteği',
    phase: 'Faz 9',
    description: 'Hormon testleri, glisemik veriler, metabolik ölçümler ve ilaç takibini birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Endokrinoloji çalışma alanı',
    summaryTitle: 'AI Endokrinoloji Özeti',
    plannedFeatures: ['Tiroid paneli değerlendirmesi', 'Glukoz ve HbA1c trendleri', 'Hipofiz ve adrenal eksen görünümü', 'Metabolik risk değerlendirmesi', 'Tedavi yanıtı ve doz değişikliği zaman çizelgesi'],
    dataSources: ['TSH / fT4', 'Glukoz', 'HbA1c', 'Kortizol', 'İnsülin', 'Lipit paneli'],
    disclaimer: 'Bu modül endokrinoloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  oncology: {
    title: 'Onkoloji',
    eyebrow: 'Onkolojik Klinik Karar Desteği',
    phase: 'Faz 9.5',
    description: 'Patoloji, görüntüleme, tümör belirteçleri ve tedavi yanıtını ortak bir zaman çizelgesinde değerlendirmek için planlanan modül.',
    workspaceTitle: 'Onkoloji çalışma alanı',
    summaryTitle: 'AI Onkoloji Özeti',
    plannedFeatures: ['Patoloji ve görüntüleme bulgularının birleştirilmesi', 'Tümör belirteci trendleri', 'Tedavi yanıtı karşılaştırması', 'Yan etki ve toksisite izlemi', 'Multidisipliner kurul özeti oluşturma'],
    dataSources: ['Patoloji', 'PET/BT', 'BT / MR', 'Tümör belirteçleri', 'Tedavi protokolü', 'Laboratuvar'],
    disclaimer: 'Bu modül onkoloji uzmanı ve multidisipliner kurul değerlendirmesinin yerine geçmez.',
  },
  rheumatology: {
    title: 'Romatoloji',
    eyebrow: 'Romatolojik Karar Desteği',
    phase: 'Faz 10',
    description: 'Otoantikorlar, inflamasyon belirteçleri, semptomlar ve organ tutulumlarını birlikte izlemek için planlanan modül.',
    workspaceTitle: 'Romatoloji çalışma alanı',
    summaryTitle: 'AI Romatoloji Özeti',
    plannedFeatures: ['Otoantikor paneli görünümü', 'Hastalık aktivitesi trendleri', 'Organ tutulumu eşleştirmesi', 'Tedavi yanıtı ve yan etki takibi', 'Alevlenme açısından erken uyarı desteği'],
    dataSources: ['ANA / ENA', 'RF / Anti-CCP', 'CRP / ESR', 'Kompleman', 'Klinik muayene', 'Görüntüleme'],
    disclaimer: 'Bu modül romatoloji uzmanı değerlendirmesinin yerine geçmez.',
  },
  pediatrics: {
    title: 'Pediatri',
    eyebrow: 'Pediatrik Klinik Karar Desteği',
    phase: 'Faz 10.5',
    description: 'Yaşa özgü referanslar, büyüme verileri, aşılar ve pediatrik klinik bulguları birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Pediatri çalışma alanı',
    summaryTitle: 'AI Pediatri Özeti',
    plannedFeatures: ['Yaşa göre laboratuvar referansları', 'Büyüme eğrileri ve persentiller', 'Aşı ve gelişim takibi', 'Pediatrik doz ve risk uyarıları', 'Yenidoğan ve çocuk klinik zaman çizelgesi'],
    dataSources: ['Yaş / kilo / boy', 'Persentiller', 'Laboratuvar', 'Aşı kaydı', 'Gelişim notları', 'Vital bulgular'],
    disclaimer: 'Bu modül pediatri uzmanı değerlendirmesinin yerine geçmez.',
  },
  'obstetrics-gynecology': {
    title: 'Kadın Hastalıkları ve Doğum',
    eyebrow: 'Jinekoloji ve Obstetri Karar Desteği',
    phase: 'Faz 11',
    description: 'Gebelik takibi, hormonlar, obstetrik ultrason ve jinekolojik klinik verileri birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Kadın hastalıkları ve doğum çalışma alanı',
    summaryTitle: 'AI Kadın Sağlığı Özeti',
    plannedFeatures: ['Gebelik haftasına göre takip görünümü', 'Obstetrik USG ölçümleri', 'Fetal gelişim trendleri', 'Jinekolojik laboratuvar ve görüntüleme eşleştirmesi', 'Riskli gebelik uyarı desteği'],
    dataSources: ['Obstetrik USG', 'Gebelik laboratuvarları', 'Hormon paneli', 'Vital bulgular', 'Fetal ölçümler', 'Klinik notlar'],
    disclaimer: 'Bu modül kadın hastalıkları ve doğum uzmanı değerlendirmesinin yerine geçmez.',
  },
  'emergency-medicine': {
    title: 'Acil Tıp',
    eyebrow: 'Zaman Kritik Klinik Karar Desteği',
    phase: 'Faz 11.5',
    description: 'Vital bulgular, laboratuvar, görüntüleme ve triyaj verilerini zaman odaklı bir ekranda birleştirmek için planlanan modül.',
    workspaceTitle: 'Acil tıp çalışma alanı',
    summaryTitle: 'AI Acil Klinik Özeti',
    plannedFeatures: ['Triyaj ve öncelik görünümü', 'Zaman kritik sonuç uyarıları', 'Sepsis, inme ve kardiyak risk desteği', 'Hızlı tetkik zaman çizelgesi', 'Devir ve konsültasyon özeti'],
    dataSources: ['Vital bulgular', 'EKG', 'Laboratuvar', 'Röntgen / BT', 'Triyaj notu', 'İlaç uygulamaları'],
    disclaimer: 'Bu modül acil tıp uzmanı değerlendirmesinin ve yerel klinik protokollerin yerine geçmez.',
  },
};

function StethoscopeIcon() {
  return (
    <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3v5a6 6 0 0 0 12 0V3" />
      <path d="M6 3H4M18 3h2" />
      <path d="M12 14v2a4 4 0 0 0 4 4h1" />
      <circle cx="19" cy="20" r="2" />
    </svg>
  );
}

export default function ClinicalSpecialtyPreviewPage({ specialty }: { specialty: ClinicalSpecialty }) {
  const config = SPECIALTIES[specialty];

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">{config.eyebrow}</p>
          <div className="mt-3 flex items-center gap-3 text-cyan-700">
            <StethoscopeIcon />
            <h1 className="text-3xl font-bold tracking-tight text-slate-950">{config.title}</h1>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600">{config.description}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full bg-blue-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-blue-800">{config.phase}</span>
          <span className="rounded-full bg-amber-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-amber-800">Ön izleme</span>
        </div>
      </header>

      <SectionCard title={config.workspaceTitle} description="Planlanan klinik iş akışının görsel ön izlemesi. Modül etkinleştirildiğinde yetkilendirilmiş klinik verilerle çalışacak şekilde planlanmaktadır.">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.85fr)]">
          <div className="flex min-h-[340px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-950 px-6 text-center text-white">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/10 text-cyan-200"><StethoscopeIcon /></div>
            <p className="mt-5 text-lg font-semibold">Klinik veri çalışma alanı</p>
            <p className="mt-2 text-sm font-medium text-cyan-200">Hasta özeti · tetkikler · zaman çizelgesi</p>
            <p className="mt-4 max-w-md text-sm leading-6 text-slate-300">Branşa özgü klinik veriler, önemli değişimler ve hekim notları bu alanda birlikte gösterilecek.</p>
            <span className="mt-6 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-300">Modül aktif değil</span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="font-semibold text-slate-950">{config.summaryTitle}</h2>
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50/70 p-4 text-sm text-blue-900">Bu modül geliştirme aşamasındadır. Henüz gerçek analiz sonucu üretmez.</div>
            <div className="mt-5">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Planlanan özellikler</p>
              <ul className="mt-3 space-y-3">
                {config.plannedFeatures.map((feature) => (
                  <li key={feature} className="flex gap-3 text-sm leading-6 text-slate-700">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-600" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-5">
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">Planlanan veri kaynakları</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {config.dataSources.map((item) => <span key={item} className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700">{item}</span>)}
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
          <strong>Geliştirme bildirimi:</strong> {config.disclaimer}
        </div>
      </SectionCard>
    </div>
  );
}
