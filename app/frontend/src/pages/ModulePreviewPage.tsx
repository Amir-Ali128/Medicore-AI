import type { ReactNode } from 'react';

import SectionCard from '../components/ui/SectionCard';

type PreviewModule = 'imaging' | 'pathology' | 'cardiology';

type ModuleConfig = {
  eyebrow: string;
  title: string;
  phase: string;
  status: string;
  description: string;
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
  icon: ReactNode;
};

const MODULES: Record<PreviewModule, ModuleConfig> = {
  imaging: {
    eyebrow: 'Radyoloji İncelemesi',
    title: 'Medikal Görüntüleme',
    phase: 'Faz 2',
    status: 'Ön izleme',
    description:
      'Röntgen, BT, MR, ultrason ve PET/BT görüntülerini tek bir klinik çalışma alanında incelemek için planlanan modül.',
    viewerTitle: 'Görüntü alanı',
    viewerSubtitle: 'DICOM Viewer ön izlemesi',
    viewerHint: 'Görüntü yükleme, seri gezintisi ve temel ölçüm araçları burada yer alacak.',
    findingsTitle: 'AI Bulguları',
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
    icon: <span aria-hidden="true">🩻</span>,
  },
  pathology: {
    eyebrow: 'Dijital Patoloji',
    title: 'Patoloji',
    phase: 'Faz 3',
    status: 'Ön izleme',
    description:
      'Dijital preparatlar üzerinde hücre, doku ve şüpheli alan analizi için planlanan patoloji çalışma alanı.',
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
    icon: <span aria-hidden="true">🧫</span>,
  },
  cardiology: {
    eyebrow: 'Kardiyoloji Karar Desteği',
    title: 'Kardiyoloji',
    phase: 'Faz 3.1',
    status: 'Ön izleme',
    description:
      'EKG, EKO, Holter, kardiyak görüntüleme ve laboratuvar verilerini birlikte değerlendirmek için planlanan modül.',
    viewerTitle: 'Kardiyak veri alanı',
    viewerSubtitle: 'EKG · EKO · Holter ön izlemesi',
    viewerHint: 'Sinyal, video ve rapor verileri bu alanda ortak bir hasta zaman çizelgesinde gösterilecek.',
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
    accentClass: 'border-rose-200 bg-rose-50/70 text-rose-900',
    badgeClass: 'bg-rose-100 text-rose-800',
    icon: <span aria-hidden="true">🫀</span>,
  },
};

function EmptyViewer({ config }: { config: ModuleConfig }) {
  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-slate-950 px-6 text-center text-white">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-white/10 text-3xl">
        {config.icon}
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
            <span className="text-3xl">{config.icon}</span>
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
        title={`${config.title} çalışma alanı`}
        description="Planlanan klinik iş akışının görsel ön izlemesi. Aktif özellikler açıldığında bu alan gerçek hasta verisiyle çalışacaktır."
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.8fr)]">
          <EmptyViewer config={config} />

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-semibold text-slate-950">{config.findingsTitle}</h2>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-600">
                Yakında
              </span>
            </div>

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
      </SectionCard>

      <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-950">
        <strong>Geliştirme bildirimi:</strong> {config.disclaimer}
      </div>
    </div>
  );
}
