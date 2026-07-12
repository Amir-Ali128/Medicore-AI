import { useEffect } from 'react';

const EXACT_TRANSLATIONS: Record<string, string> = {
  'Unknown patient': 'Bilinmeyen hasta',
  'Extracted from uploaded PDF': 'Yüklenen PDF’den alındı',
  'PDF metadata not available': 'PDF’de hasta bilgisi bulunamadı',
  'Current workflow': 'Mevcut işlem',
  Loading: 'Yükleniyor',
  'Loading…': 'Yükleniyor…',
  Save: 'Kaydet',
  Cancel: 'İptal',
  Delete: 'Sil',
  Edit: 'Düzenle',
  Close: 'Kapat',
  Back: 'Geri',
  Continue: 'Devam et',
  Open: 'Aç',
  Refresh: 'Yenile',
  Search: 'Ara',
  'No data': 'Veri bulunamadı',
  'No results': 'Sonuç bulunamadı',
  Dashboard: 'Hasta Özeti',
  'Patient Detail': 'Hasta Kaydı',
  'Lab Analysis': 'Laboratuvar',
  Results: 'Sonuçlar',
  Timeline: 'Geçmiş',
  'Doctor Review': 'Hekim Değerlendirmesi',
  'Doctor Worklist': 'Hekim İşlemleri',
  'Clinical Review Prompts': 'Klinik Değerlendirmeler',
  'PDF upload': 'PDF Yükleme',
  'Manual entry': 'Manuel Giriş',
  Selected: 'Seçilen dosya',
  'Upload & Analyze PDF': 'PDF’yi Yükle ve Analiz Et',
  'Uploading & analyzing...': 'PDF yükleniyor ve analiz ediliyor…',
  'Save & Analyze Manual Results': 'Sonuçları Kaydet ve Analiz Et',
  'Saving & analyzing...': 'Kaydediliyor ve analiz ediliyor…',
  'Controlled backend sample': 'Örnek Analiz',
  'Run demo Hemoglobin payload': 'Örnek hemoglobin sonucunu analiz et',
  'Run Backend Analysis': 'Örnek Analizi Başlat',
  'Running...': 'Analiz ediliyor…',
  'Analysis completed.': 'Analiz tamamlandı.',
  'View Full Analysis Record': 'Tüm Sonuçları Gör',
  'Analysis summary': 'Laboratuvar Özeti',
  'Processed results': 'Toplam Sonuç',
  'High signals': 'Yüksek Değerler',
  'Low signals': 'Düşük Değerler',
  'Needs review': 'Hekim Kontrolü Gerekenler',
  'All values processed by the deterministic pipeline.': 'Analiz edilen toplam sonuç sayısı.',
  'Above an available reference range.': 'Referans aralığının üzerinde.',
  'Below an available reference range.': 'Referans aralığının altında.',
  'Unknown or uncertain results separated for review.': 'Belirsiz sonuçlar hekim kontrolü için ayrıldı.',
  'Abnormal and review-required results': 'Anormal ve Kontrol Gereken Sonuçlar',
  'Complete an analysis to build the review queue.': 'Sonuçları görmek için önce bir analiz oluşturun.',
  'No abnormal or review-required result was found. Normal rows remain hidden by design.':
    'Anormal veya kontrol gerektiren sonuç bulunmadı.',
  'High results': 'Yüksek Sonuçlar',
  'Low results': 'Düşük Sonuçlar',
  'Claude clinical copilot': 'Yapay Zekâ Klinik Değerlendirmesi',
  'Evaluate abnormal results': 'Anormal Sonuçları Değerlendir',
  'Evaluate with Claude': 'Tüm Verilerle Değerlendir',
  'Claude is evaluating...': 'Değerlendiriliyor…',
  'Complete an analysis before evaluating the results with Claude.':
    'Klinik değerlendirme için önce laboratuvar analizi oluşturun.',
  'Continue the workflow': 'Sonraki İşlemler',
  'View Analysis Results': 'Laboratuvar Sonuçlarını Aç',
  'Open Clinical Review Prompts': 'Klinik Değerlendirmeleri Aç',
  'Open Timeline': 'Geçmişi Aç',
  'Latest report status': 'Son rapor durumu',
  'Doctor review pending': 'Hekim değerlendirmesi bekleniyor',
  'Doctor action recorded': 'Hekim işlemi kaydedildi',
  'Analysis ready': 'Analiz hazır',
  'Pending doctor reviews': 'Bekleyen hekim değerlendirmeleri',
  'Abnormal lab signals': 'Anormal laboratuvar sonuçları',
  'Timeline events': 'Geçmiş işlemler',
  'Latest report summary': 'Son rapor özeti',
  'Report source': 'Rapor kaynağı',
  'Analysis status': 'Analiz durumu',
  'Clinical review prompt status': 'Klinik değerlendirme durumu',
  'Doctor review status': 'Hekim değerlendirme durumu',
  'Patient visibility': 'Hasta görünürlüğü',
  'Patient workflow shortcuts': 'Hızlı işlemler',
  'View analysis results': 'Sonuçları görüntüle',
  'Clinical review prompts': 'Klinik değerlendirmeler',
  'Doctor review': 'Hekim değerlendirmesi',
  'Doctor worklist': 'Hekim işlemleri',
  'Lab signal summary': 'Laboratuvar özeti',
  'Recent timeline preview': 'Son işlemler',
  'Analysis run selected': 'Analiz seçildi',
  'Structured lab results loaded': 'Laboratuvar sonuçları yüklendi',
  Intake: 'Hasta kaydı',
  'Frontend workflow': 'Sistem işlemi',
  'Lab analysis': 'Laboratuvar analizi',
  'Backend analysis service': 'Analiz sistemi',
  'Clinical review prompt': 'Klinik değerlendirme',
  'Doctor reviewer': 'Değerlendiren hekim',
  'Doctor review workflow': 'Hekim değerlendirmesi',
  'Review status breakdown': 'Değerlendirme durumu',
  Pending: 'Bekliyor',
  Approved: 'Onaylandı',
  Rejected: 'Reddedildi',
  'Extra test requested': 'Ek test istendi',
  'Latest prompt': 'Son değerlendirme',
  Severity: 'Önem düzeyi',
  Evidence: 'Dayanak bulgular',
  'Safety framing': 'Güvenlik bilgisi',
  'Final clinical decisions belong to a physician.': 'Nihai klinik karar hekime aittir.',
  'Backend-connected patient': 'Aktif hasta kaydı',
  Name: 'Ad Soyad',
  Age: 'Yaş',
  Sex: 'Cinsiyet',
  'Analysis run:': 'Analiz:',
  'Lab report:': 'Laboratuvar raporu:',
  'Not stored locally': 'Kaydedilmedi',
  'Reference:': 'Referans:',
  Marker: 'Test',
  Value: 'Sonuç',
  'Measured value': 'Ölçülen değer',
  Reference: 'Referans Aralığı',
  'Reference range': 'Referans Aralığı',
  Status: 'Durum',
  Reason: 'Açıklama',
  'Review note': 'Açıklama',
  NORMAL: 'NORMAL',
  HIGH: 'YÜKSEK',
  LOW: 'DÜŞÜK',
  UNKNOWN: 'BELİRSİZ',
  'NEEDS REVIEW': 'HEKİM KONTROLÜ',
  'PENDING REVIEW': 'HEKİM ONAYI BEKLİYOR',
  COMPLETED: 'TAMAMLANDI',
  CREATED: 'OLUŞTURULDU',
  BLOCKED: 'KAPALI',
  PENDING: 'BEKLİYOR',
  APPROVED: 'ONAYLANDI',
  REJECTED: 'REDDEDİLDİ',
  'EXTRA TEST REQUESTED': 'EK TEST İSTENDİ',
  MODERATE: 'ORTA',
};

const REGEX_TRANSLATIONS: Array<[RegExp, (...matches: string[]) => string]> = [
  [/^Value (.+) is within reference range \[(.+), (.+)\]\.$/, (_all, value, min, max) => `Değer ${value}, [${min}, ${max}] referans aralığındadır.`],
  [/^Value (.+) is above reference maximum (.+)\.$/, (_all, value, max) => `Değer ${value}, ${max} üst sınırının üzerindedir.`],
  [/^Value (.+) is below reference minimum (.+)\.$/, (_all, value, min) => `Değer ${value}, ${min} alt sınırının altındadır.`],
  [/^(\d+) structured lab result row loaded\.$/, (_all, count) => `${count} laboratuvar sonucu yüklendi.`],
  [/^(\d+) clinical review prompt available\.$/, (_all, count) => `${count} klinik değerlendirme mevcut.`],
  [/^(\d+) result\(s\)$/, (_all, count) => `${count} sonuç`],
  [/^Claude prepared (\d+) physician-review evaluation\(s\)\.$/, (_all, count) => `${count} klinik değerlendirme hazırlandı.`],
];

const TECHNICAL_REPLACEMENTS: Array<[RegExp, string]> = [
  [/\bMock\b/gi, 'Örnek'],
  [/\bDemo\b/gi, 'Örnek'],
  [/\bBackend\b/gi, 'Sistem'],
  [/\bFrontend\b/gi, 'Arayüz'],
  [/\bPipeline\b/gi, 'Analiz süreci'],
  [/\bReview Prompt(s)?\b/gi, 'Klinik değerlendirme'],
  [/\bPrompt(s)?\b/gi, 'Değerlendirme'],
  [/\bClinical Hypotheses\b/gi, 'Klinik Değerlendirmeler'],
  [/\bClinical Hypothesis\b/gi, 'Klinik Değerlendirme'],
  [/\bConfidence Score\b/gi, 'Güven düzeyi'],
  [/\bModel confidence\b/gi, 'Güven düzeyi'],
  [/\bGenerated by Claude\b/gi, 'Yapay zekâ değerlendirmesi'],
  [/\bMetadata\b/gi, 'Ek bilgiler'],
  [/\bDraft(s)?\b/gi, 'Taslak'],
];

function translateText(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return value;

  const exact = EXACT_TRANSLATIONS[trimmed];
  if (exact) return value.replace(trimmed, exact);

  for (const [pattern, replacement] of REGEX_TRANSLATIONS) {
    const match = trimmed.match(pattern);
    if (match) return value.replace(trimmed, replacement(...match));
  }

  let translated = value;
  for (const [pattern, replacement] of TECHNICAL_REPLACEMENTS) {
    translated = translated.replace(pattern, replacement);
  }
  return translated;
}

function localizeElementAttributes(element: Element) {
  for (const attributeName of ['placeholder', 'title', 'aria-label']) {
    const current = element.getAttribute(attributeName);
    if (!current) continue;
    const translated = translateText(current);
    if (translated !== current) element.setAttribute(attributeName, translated);
  }

  if (element instanceof HTMLOptionElement) {
    const translated = translateText(element.textContent ?? '');
    if (translated !== element.textContent) element.textContent = translated;
  }
}

function localizeNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const textNode = root as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
      const translated = translateText(textNode.nodeValue ?? '');
      if (translated !== textNode.nodeValue) textNode.nodeValue = translated;
    }
    return;
  }

  if (root instanceof Element) localizeElementAttributes(root);

  const walker = document.createTreeWalker(
    root,
    NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
  );
  let current = walker.nextNode();
  while (current) {
    if (current.nodeType === Node.ELEMENT_NODE) {
      localizeElementAttributes(current as Element);
    } else {
      const textNode = current as Text;
      const parent = textNode.parentElement;
      if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
        const translated = translateText(textNode.nodeValue ?? '');
        if (translated !== textNode.nodeValue) textNode.nodeValue = translated;
      }
    }
    current = walker.nextNode();
  }
}

export default function FrontendTurkishLocalizer() {
  useEffect(() => {
    localizeNode(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          localizeNode(mutation.target);
        } else {
          for (const node of mutation.addedNodes) localizeNode(node);
        }
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
