import { useEffect } from 'react';

const EXACT: Record<string, string> = {
  'Demo Doctor': 'Demo Hekim',
  'Example Doctor': 'Örnek Hekim',
  'Demo Patient': 'Demo Hasta',
  'Example Patient': 'Örnek Hasta',
  Patient: 'Hasta',
  Doctor: 'Hekim',
  'Doctor Review': 'Hekim Değerlendirmesi',
  'Doctor review panel': 'Hekim Değerlendirme Ekranı',
  'Doctor Worklist': 'Hekim İş Listesi',
  'Review case summary': 'Vaka Özeti',
  'Selected review prompt': 'Seçili Klinik Değerlendirme',
  'Pending prompts': 'Bekleyen Değerlendirmeler',
  'Evidence signals': 'Dayanak Bulgular',
  'Latest generated': 'Son Oluşturulma',
  'Patient visibility': 'Hasta Görünürlüğü',
  'Blocked until physician approval': 'Hekim onayına kadar hasta ekranında gösterilmez',
  'Review selected prompt': 'Seçili Değerlendirmeyi İncele',
  'Backend actions enabled': 'Hekim İşlemleri Aktif',
  Approve: 'Onayla',
  Reject: 'Reddet',
  'Request extra test': 'Ek Tetkik İste',
  'No pending doctor reviews': 'Bekleyen hekim değerlendirmesi yok',
  'Loading doctor review': 'Hekim değerlendirmesi yükleniyor',
  'Unable to load doctor review': 'Hekim değerlendirmesi yüklenemedi',
  Confidence: 'Güven Düzeyi',
  Priority: 'Öncelik',
  'high priority': 'yüksek öncelik',
  'medium priority': 'orta öncelik',
  'low priority': 'düşük öncelik',
  'Review focus': 'İnceleme Odağı',
  Summary: 'Özet',
  Findings: 'Bulgular',
  Recommendation: 'Öneri',
  Recommendations: 'Öneriler',
  Interpretation: 'Klinik Yorum',
  'Clinical interpretation': 'Klinik Yorum',
  'Clinical assessment': 'Klinik Değerlendirme',
  'Clinical decision support': 'Klinik Karar Desteği',
  'Needs physician review': 'Hekim Değerlendirmesi Gerekli',
  'Physician review required': 'Hekim Değerlendirmesi Gerekli',
  'Not a diagnosis': 'Tanı değildir',
  'Reference range': 'Referans Aralığı',
  'Measured value': 'Ölçülen Değer',
  'Previous value': 'Önceki Değer',
  Change: 'Değişim',
  Trend: 'Seyir',
  'Critical value': 'Kritik Değer',
  Abnormal: 'Anormal',
  Normal: 'Normal',
  High: 'Yüksek',
  Low: 'Düşük',
  Unknown: 'Belirsiz',
  Pending: 'Bekliyor',
  Approved: 'Onaylandı',
  Rejected: 'Reddedildi',
  Completed: 'Tamamlandı',
  'In progress': 'Devam Ediyor',
  'No data available': 'Görüntülenecek veri yok',
  'No patient selected': 'Hasta seçilmedi',
  'Select patient': 'Hasta Seç',
  'Patient summary': 'Hasta Özeti',
  'Patient history': 'Hasta Geçmişi',
  'Clinical notes': 'Klinik Notlar',
  Medications: 'İlaçlar',
  Allergies: 'Alerjiler',
  Diagnoses: 'Tanılar',
  'Vital signs': 'Yaşamsal Bulgular',
  'Lab results': 'Laboratuvar Sonuçları',
  'Radiology reports': 'Radyoloji Raporları',
  'Generated at': 'Oluşturulma Zamanı',
  'Last updated': 'Son Güncelleme',
  'Data source': 'Veri Kaynağı',
  'AI summary': 'Yapay Zekâ Özeti',
  'AI findings': 'Yapay Zekâ Bulguları',
  'Model output': 'Sistem Çıktısı',
  'System output': 'Sistem Çıktısı',
  'Supporting evidence': 'Destekleyici Bulgular',
  'Missing data': 'Eksik Veri',
  'Additional tests': 'Ek Tetkikler',
  'Follow-up recommended': 'Takip Önerilir',
  'Urgent review': 'Acil Değerlendirme',
};

const REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bbackend\b/gi, 'sistem'],
  [/\bfrontend\b/gi, 'arayüz'],
  [/\bworkflow\b/gi, 'iş akışı'],
  [/\bprompt(s)?\b/gi, 'değerlendirme'],
  [/\breview queue\b/gi, 'inceleme sırası'],
  [/\bpending queue\b/gi, 'bekleyen değerlendirmeler'],
  [/\bphysician\b/gi, 'hekim'],
  [/\bdoctor\b/gi, 'hekim'],
  [/\bpatient\b/gi, 'hasta'],
  [/\bevidence\b/gi, 'dayanak bulgu'],
  [/\bconfidence\b/gi, 'güven düzeyi'],
  [/\bseverity\b/gi, 'önem düzeyi'],
  [/\bpriority\b/gi, 'öncelik'],
  [/\bgenerated\b/gi, 'oluşturuldu'],
  [/\bselected\b/gi, 'seçili'],
  [/\bpending\b/gi, 'bekliyor'],
  [/\bblocked\b/gi, 'gizli'],
  [/\bapproval\b/gi, 'onay'],
  [/\banalysis\b/gi, 'analiz'],
  [/\bassessment\b/gi, 'değerlendirme'],
  [/\bsummary\b/gi, 'özet'],
  [/\bfindings\b/gi, 'bulgular'],
  [/\brecommendation(s)?\b/gi, 'öneriler'],
];

function translate(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return value;
  if (EXACT[trimmed]) return value.replace(trimmed, EXACT[trimmed]);

  let translated = value;
  for (const [pattern, replacement] of REPLACEMENTS) {
    translated = translated.replace(pattern, replacement);
  }
  return translated;
}

function localize(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const node = root as Text;
    const parent = node.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
      const next = translate(node.nodeValue ?? '');
      if (next !== node.nodeValue) node.nodeValue = next;
    }
    return;
  }

  if (root instanceof Element) {
    for (const attribute of ['placeholder', 'title', 'aria-label']) {
      const current = root.getAttribute(attribute);
      if (!current) continue;
      const next = translate(current);
      if (next !== current) root.setAttribute(attribute, next);
    }
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let current = walker.nextNode();
  while (current) {
    if (current.nodeType === Node.TEXT_NODE) {
      const node = current as Text;
      const parent = node.parentElement;
      if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
        const next = translate(node.nodeValue ?? '');
        if (next !== node.nodeValue) node.nodeValue = next;
      }
    } else if (current instanceof Element) {
      for (const attribute of ['placeholder', 'title', 'aria-label']) {
        const value = current.getAttribute(attribute);
        if (!value) continue;
        const next = translate(value);
        if (next !== value) current.setAttribute(attribute, next);
      }
    }
    current = walker.nextNode();
  }
}

export default function DoctorFriendlyTurkish() {
  useEffect(() => {
    localize(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') localize(mutation.target);
        for (const node of mutation.addedNodes) localize(node);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    return () => observer.disconnect();
  }, []);

  return null;
}
