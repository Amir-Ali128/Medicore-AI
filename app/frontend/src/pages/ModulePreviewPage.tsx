import type { ReactNode } from 'react';

import SectionCard from '../components/ui/SectionCard';

type PreviewModule = 'radiology' | 'imaging' | 'pathology' | 'cardiology' | 'microbiology';
type IconName = 'file-scan' | 'scan' | 'microscope' | 'heart' | 'microbe';

type ModuleConfig = {
  eyebrow: string;
  title: string;
  phase: string;
  status: string;
  description: string;
  workspaceTitle: string;
  viewerTitle: string;
  viewerSubtitle: string;
  viewerHint: string;
  findingsTitle: string;
  plannedFeatures: string[];
  supportedDataTitle: string;
  supportedData: string[];
  disclaimer: string;
  accentClass: string;
  badgeClass: string;
  icon: IconName;
};

function ClinicalIcon({ name, className = 'h-8 w-8' }: { name: IconName; className?: string }) {
  const common = {
    className,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };

  if (name === 'file-scan') {
    return (
      <svg {...common}>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M8 13h2M8 17h2M14 13h2M14 17h2" />
      </svg>
    );
  }

  if (name === 'scan') {
    return (
      <svg {...common}>
        <path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />
        <rect x="7" y="7" width="10" height="10" rx="2" />
        <path d="M9 12h6" />
      </svg>
    );
  }

  if (name === 'microscope') {
    return (
      <svg {...common}>
        <path d="m6 18 3-3M9 15l-2-2 5-5 2 2-5 5zM13 5l2-2 3 3-2 2M12 19h8M5 21h16" />
        <path d="M14 13a5 5 0 0 1 5 5" />
      </svg>
    );
  }

  if (name === 'heart') {
    return (
      <svg {...common}>
        <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z" />
        <path d="M3.5 12h4l1.5-3 3 6 1.5-3h7" />
      </svg>
    );
  }

  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="7" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
      <circle cx="10" cy="11" r="1" />
      <circle cx="14.5" cy="13.5" r="1" />
    </svg>
  );
}

const MODULES: Record<PreviewModule, ModuleConfig> = {
  radiology: {
    eyebrow: 'Radyoloji Rapor Analizi',
    title: 'Radyoloji Raporları',
    phase: 'Faz 2',
    status: 'Ön izleme',
    description:
      'Radyoloji raporlarını yapılandırılmış bulgulara dönüştürmek ve klinik bağlamla birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Rapor değerlendirme alanı',
    viewerTitle: 'Rapor çalışma alanı',
    viewerSubtitle: 'PDF ve metin raporu ön izlemesi',
    viewerHint: 'Rapor yükleme, metin doğrulama ve bulgu inceleme araçları bu alanda yer alacak.',
    findingsTitle: 'AI Rapor Özeti',
    plannedFeatures: [
      'PDF ve metin raporlarının ayrıştırılması',
      'Bulguların yapılandırılmış olarak sınıflandırılması',
      'Kritik ifadelerin işaretlenmesi',
      'Önceki raporlarla karşılaştırma',
      'Laboratuvar ve klinik verilerle birlikte değerlendirme',
    ],
    supportedDataTitle: 'Planlanan rapor türleri',
    supportedData: ['Röntgen raporu', 'BT raporu', 'MR raporu', 'USG raporu', 'PET/BT raporu'],
    disclaimer: 'Bu modül klinik kullanım için henüz aktif değildir.',
    accentClass: 'border-sky-200 bg-sky-50/70 text-sky-900',
    badgeClass: 'bg-sky-100 text-sky-800',
    icon: 'file-scan',
  },
  imaging: {
    eyebrow: 'Medikal Görüntüleme',
    title: 'Görüntüleme AI',
    phase: 'Faz 2.5',
    status: 'Ön izleme',
    description:
      'Röntgen, BT, MR, ultrason ve PET/BT görüntülerini doğrudan incelemek için planlanan görüntüleme çalışma alanı.',
    workspaceTitle: 'Görüntü inceleme alanı',
    viewerTitle: 'DICOM görüntüleyici',
    viewerSubtitle: 'Medikal görüntü ön izlemesi',
    viewerHint: 'Seri gezintisi, ölçüm araçları ve şüpheli bölge işaretlemeleri burada yer alacak.',
    findingsTitle: 'AI Görüntüleme Bulguları',
    plannedFeatures: [
      'Bulguların yapılandırılmış olarak çıkarılması',
      'Şüpheli bölgelerin görsel olarak işaretlenmesi',
      'Model güveni ve belirsizlik bilgisinin gösterilmesi',
      'Önceki tetkiklerle karşılaştırma',
      'Radyoloji raporuyla birlikte değerlendirme',
    ],
    supportedDataTitle: 'Planlanan modaliteler',
    supportedData: ['Röntgen', 'BT', 'MR', 'Ultrason', 'PET/BT'],
    disclaimer: 'Bu modül henüz görüntü analizi veya klinik kullanım için aktif değildir.',
    accentClass: 'border-cyan-200 bg-cyan-50/70 text-cyan-900',
    badgeClass: 'bg-cyan-100 text-cyan-800',
    icon: 'scan',
  },
  pathology: {
    eyebrow: 'Dijital Patoloji',
    title: 'Patoloji',
    phase: 'Faz 3',
    status: 'Ön izleme',
    description:
      'Dijital preparatlar üzerinde hücre, doku ve şüpheli alan analizi için planlanan patoloji çalışma alanı.',
    workspaceTitle: 'Patoloji inceleme alanı',
    viewerTitle: 'Preparat görüntüleyici',
    viewerSubtitle: 'Whole Slide Image ön izlemesi',
    viewerHint: 'Büyük preparat görüntülerinde yakınlaştırma, bölge seçimi ve anotasyon araçları burada yer alacak.',
    findingsTitle: 'AI Patoloji Bulguları',
    plannedFeatures: [
      'Hücre ve çekirdek tespiti',
      'Doku segmentasyonu',
      'Şüpheli alanların işaretlenmesi',
      'Tümör sınıflandırma desteği',
      'Mitotik aktivite ve yoğunluk analizi',
    ],
    supportedDataTitle: 'Planlanan dosya desteği',
    supportedData: ['SVS', 'TIFF', 'NDPI', 'JPG', 'PNG'],
    disclaimer: 'Patoloji çıktıları uzman hekim değerlendirmesi olmadan kullanılmamalıdır.',
    accentClass: 'border-violet-200 bg-violet-50/70 text-violet-900',
    badgeClass: 'bg-violet-100 text-violet-800',
    icon: 'microscope',
  },
  cardiology: {
    eyebrow: 'Kardiyoloji Karar Desteği',
    title: 'Kardiyoloji',
    phase: 'Faz 3.1',
    status: 'Ön izleme',
    description:
      'EKG, EKO, Holter, kardiyak görüntüleme ve laboratuvar verilerini birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Kardiyoloji çalışma alanı',
    viewerTitle: 'Kardiyak veri alanı',
    viewerSubtitle: 'EKG · EKO · Holter ön izlemesi',
    viewerHint: 'Sinyal, video ve rapor verileri ortak bir hasta zaman çizelgesinde gösterilecek.',
    findingsTitle: 'AI Kardiyoloji Özeti',
    plannedFeatures: [
      'Ritim ve aritmi analizi',
      'ST-T değişikliği değerlendirmesi',
      'EKO ölçümleri ve EF tahmini',
      'Holter olaylarının sınıflandırılması',
      'Kardiyak risk skorlarının hesaplanması',
    ],
    supportedDataTitle: 'İlgili veri kaynakları',
    supportedData: ['EKG', 'EKO', 'Holter', 'Troponin', 'CK-MB', 'BNP / NT-proBNP'],
    disclaimer: 'Bu modül henüz aktif değildir ve kardiyoloji uzmanı değerlendirmesinin yerine geçmez.',
    accentClass: 'border-blue-200 bg-blue-50/70 text-blue-900',
    badgeClass: 'bg-blue-100 text-blue-800',
    icon: 'heart',
  },
  microbiology: {
    eyebrow: 'Klinik Mikrobiyoloji',
    title: 'Mikrobiyoloji',
    phase: 'Faz 3.2',
    status: 'Ön izleme',
    description:
      'Kültür, antibiyogram, moleküler test ve mikroskopi sonuçlarını birlikte değerlendirmek için planlanan modül.',
    workspaceTitle: 'Mikrobiyoloji çalışma alanı',
    viewerTitle: 'Mikrobiyoloji veri alanı',
    viewerSubtitle: 'Kültür · PCR · Antibiyogram ön izlemesi',
    viewerHint: 'Etken, örnek türü, duyarlılık sonuçları ve zaman içindeki değişimler burada gösterilecek.',
    findingsTitle: 'AI Mikrobiyoloji Özeti',
    plannedFeatures: [
      'Etken ve örnek türünün yapılandırılması',
      'Antibiyogram duyarlılık profilinin özetlenmesi',
      'Olası kontaminasyon ve tekrar örnek uyarıları',
      'Direnç paternlerinin zaman içinde karşılaştırılması',
      'Enfeksiyon belirteçleriyle birlikte klinik değerlendirme',
    ],
    supportedDataTitle: 'Planlanan veri kaynakları',
    supportedData: ['Kültür', 'Antibiyogram', 'PCR', 'Seroloji', 'Mikroskopi', 'MALDI-TOF'],
    disclaimer: 'Bu modül henüz aktif değildir ve mikrobiyoloji uzmanı değerlendirmesinin yerine geçmez.',
    accentClass: 'border-emerald-200 bg-emerald-50/70 text-emerald-900',
    badgeClass: 'bg-emerald-100 text-emerald-800',
    icon: 'microbe',
  },
};

function EmptyViewer({ config }: { config: ModuleConfig }) {
  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-950 px-6 text-center text-white">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/10 text-cyan-200">
        <ClinicalIcon name={config.icon} />
      </div>
      <p className="mt-5 text-lg font-semibold">{config.viewerTitle}</p>
      <p className="mt-2 text-sm font-medium text-cyan-200">{config.viewerSubtitle}</p>
      <p className="mt-4 max-w-md text-sm leading-6 text-slate-300">{config.viewerHint}</p>
      <span className="mt-6 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-300">
        Modül aktif değil
      </span>
    </div>
  );
}

export default function ModulePreviewPage({ module }: { module: PreviewModule }) {
  const config = MODULES[module];

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-700">
            {config.eyebrow}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <span className="text-cyan-700"><ClinicalIcon name={config.icon} /></span>
            <h1 className="text-3xl font-bold tracking-tight text-slate-950">{config.title}</h1>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-600">{config.description}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <span className={`rounded-full px-3 py-1.5 text-xs font-bold uppercase tracking-wide ${config.badgeClass}`}>
            {config.phase}
          </span>
          <span className="rounded-full bg-amber-100 px-3 py-1.5 text-xs font-bold uppercase tracking-wide text-amber-800">
            {config.status}
          </span>
        </div>
      </header>

      <SectionCard
        title={config.workspaceTitle}
        description="Planlanan klinik iş akışının görsel ön izlemesi. Modül etkinleştirildiğinde yetkilendirilmiş klinik verilerle çalışacak şekilde planlanmaktadır."
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.8fr)]">
          <EmptyViewer config={config} />

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="font-semibold text-slate-950">{config.findingsTitle}</h2>

            <div className={`mt-4 rounded-xl border p-4 text-sm ${config.accentClass}`}>
              Bu modül geliştirme aşamasındadır. Henüz gerçek analiz sonucu üretmez.
            </div>

            <div className="mt-5">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
                Planlanan özellikler
              </p>
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
          <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
            {config.supportedDataTitle}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {config.supportedData.map((item) => (
              <span
                key={item}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700"
              >
                {item}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
          <strong>Geliştirme bildirimi:</strong> {config.disclaimer}
        </div>
      </SectionCard>
    </div>
  );
}
