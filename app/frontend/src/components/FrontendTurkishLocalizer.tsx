import { useEffect } from 'react';

const EXACT_TRANSLATIONS: Record<string, string> = {
  'Unknown patient': 'Bilinmeyen hasta',
  'Extracted from uploaded PDF': 'Yüklenen PDF’den çıkarıldı',
  'PDF metadata not available': 'PDF hasta bilgisi bulunamadı',
  'Current workflow': 'Mevcut işlem',
  'Loading': 'Yükleniyor',
  'Loading…': 'Yükleniyor…',
  'Save': 'Kaydet',
  'Cancel': 'İptal',
  'Delete': 'Sil',
  'Edit': 'Düzenle',
  'Close': 'Kapat',
  'Back': 'Geri',
  'Continue': 'Devam et',
  'Open': 'Aç',
  'Refresh': 'Yenile',
  'Search': 'Ara',
  'No data': 'Veri bulunamadı',
  'No results': 'Sonuç bulunamadı',
  'Dashboard': 'Ana Sayfa',
  'Patient Detail': 'Hasta Kaydı',
  'Lab Analysis': 'Laboratuvar',
  'Results': 'Sonuçlar',
  'Timeline': 'Geçmiş Sonuçlar',
  'Doctor Review': 'Hekim Değerlendirmesi',
  'Doctor Worklist': 'Hekim İşlemleri',
  'Clinical Review Prompts': 'Klinik Değerlendirmeler',
  'Latest report status': 'Son rapor durumu',
  'Doctor review pending': 'Hekim değerlendirmesi bekleniyor',
  'Doctor action recorded': 'Hekim işlemi kaydedildi',
  'Analysis ready': 'Analiz hazır',
  'Backend workflow status for latest analysis run.': 'Son analizin işlem durumu.',
  'Pending doctor reviews': 'Bekleyen hekim değerlendirmeleri',
  'Clinical review prompts awaiting doctor action.': 'Hekim işlemi bekleyen değerlendirmeler.',
  'Abnormal lab signals': 'Anormal laboratuvar sonuçları',
  'LOW or HIGH lab result statuses.': 'Düşük veya yüksek laboratuvar sonuçları.',
  'Timeline events': 'Geçmiş işlemler',
  'Backend workflow events in this patient view.': 'Bu hastaya ait geçmiş işlemler.',
  'Latest report summary': 'Son rapor özeti',
  'Backend analysis and review status for the latest workflow.': 'Son analizin değerlendirme durumu.',
  'Report source': 'Rapor kaynağı',
  'Backend lab report': 'Laboratuvar raporu',
  'Latest local workflow': 'Son işlem',
  'Latest event': 'Son işlem',
  'Analysis status': 'Analiz durumu',
  'Clinical review prompt status': 'Klinik değerlendirme durumu',
  'Doctor review status': 'Hekim değerlendirme durumu',
  'Patient visibility': 'Hasta görünürlüğü',
  'Patient workflow shortcuts': 'Hızlı işlemler',
  'Backend-connected navigation for this patient workspace.': 'Bu hastaya ait hızlı işlem bağlantıları.',
  'View analysis results': 'Sonuçları görüntüle',
  'Open structured backend lab result rows.': 'Laboratuvar sonuçlarını aç.',
  'Clinical review prompts': 'Klinik değerlendirmeler',
  'Create or view generated clinical review prompts.': 'Klinik değerlendirmeleri görüntüle.',
  'Doctor review': 'Hekim değerlendirmesi',
  'Approve, reject, or request extra tests.': 'Onayla, reddet veya ek test iste.',
  'Doctor worklist': 'Hekim işlemleri',
  'View all backend review tasks.': 'Tüm hekim işlemlerini görüntüle.',
  'Lab signal summary': 'Laboratuvar sonuç özeti',
  'Structured lab signal values from backend analysis results.': 'Laboratuvar analiz sonuçları.',
  'Recent timeline preview': 'Son işlemler',
  'Latest backend workflow events for this patient.': 'Bu hastaya ait son işlemler.',
  'Analysis run selected': 'Analiz seçildi',
  'Structured lab results loaded': 'Laboratuvar sonuçları yüklendi',
  'Intake': 'Hasta kaydı',
  'Frontend workflow': 'Sistem işlemi',
  'Lab analysis': 'Laboratuvar analizi',
  'Backend analysis service': 'Analiz servisi',
  'Clinical review prompt': 'Klinik değerlendirme',
  'Doctor reviewer': 'Değerlendiren hekim',
  'Doctor review workflow': 'Hekim değerlendirmesi',
  'Clinical review prompts linked to this analysis run.': 'Bu analize bağlı klinik değerlendirmeler.',
  'Review status breakdown': 'Değerlendirme durumu',
  'Doctor review actions recorded for this patient workflow.': 'Bu hastaya ait hekim işlemleri.',
  'Pending': 'Bekliyor',
  'Approved': 'Onaylandı',
  'Rejected': 'Reddedildi',
  'Extra test requested': 'Ek test istendi',
  'Latest prompt': 'Son değerlendirme',
  'Severity': 'Önem düzeyi',
  'Confidence': 'Güven oranı',
  'Evidence': 'Dayanak',
  'Safety framing': 'Güvenlik bilgisi',
  'Patient detail shows workflow state, not medical advice.': 'Bu ekran tıbbi tavsiye değil, işlem durumunu gösterir.',
  'Patient detail events are workflow records, not diagnoses.': 'Bu kayıtlar tanı değildir.',
  'Clinical review prompts remain under physician review controls.': 'Klinik değerlendirmeler hekim kontrolündedir.',
  'Patient-facing visibility remains blocked until review rules pass.': 'Hekim değerlendirmesi tamamlanana kadar hasta görünürlüğü kapalıdır.',
  'Final clinical decisions belong to a physician.': 'Nihai klinik karar hekime aittir.',
  'Backend-connected patient': 'Aktif hasta kaydı',
  Name: 'Ad Soyad',
  Age: 'Yaş',
  Sex: 'Cinsiyet',
  'Clinical outputs are structured for physician review and are not a diagnosis.': 'Klinik çıktılar hekim değerlendirmesi içindir ve tanı değildir.',
  'Analysis run:': 'Analiz:',
  'Lab report:': 'Laboratuvar raporu:',
  'Not stored locally': 'Kaydedilmedi',
  'Reference:': 'Referans:',
  'Analysis summary': 'Analiz özeti',
  'Normal rows are excluded from the visible review queue.': 'Normal sonuçlar bu listede gösterilmez.',
  'Processed results': 'İşlenen sonuçlar',
  'High signals': 'Yüksek sonuçlar',
  'Low signals': 'Düşük sonuçlar',
  'Needs review': 'Hekim kontrolü gerekenler',
  'All values processed by the deterministic pipeline.': 'İşlenen tüm sonuçlar.',
  'Above an available reference range.': 'Referans aralığının üzerinde.',
  'Below an available reference range.': 'Referans aralığının altında.',
  'Unknown or uncertain results separated for review.': 'Belirsiz sonuçlar hekim kontrolü için ayrıldı.',
  'Separated review queue': 'Kontrol gerektiren sonuçlar',
  'Normal values are intentionally hidden from this page.': 'Normal sonuçlar bu sayfada gösterilmez.',
  'High results': 'Yüksek sonuçlar',
  'Low results': 'Düşük sonuçlar',
  Marker: 'Test',
  'Measured value': 'Ölçülen değer',
  'Reference range': 'Referans aralığı',
  Status: 'Durum',
  'Review note': 'Açıklama',
  'Backend confidence': 'Güven oranları',
  'Alias confidence': 'Test eşleşme güveni',
  'Reference confidence': 'Referans güveni',
  'Classification confidence': 'Sınıflandırma güveni',
  'Trend confidence': 'Değişim güveni',
  'Review actions': 'İlgili işlemler',
  'Generate Claude review': 'Klinik değerlendirme oluştur',
  'Open clinical review prompts': 'Klinik değerlendirmeleri aç',
  NORMAL: 'NORMAL',
  HIGH: 'YÜKSEK',
  LOW: 'DÜŞÜK',
  UNKNOWN: 'BELİRSİZ',
  'NEEDS REVIEW': 'HEKİM KONTROLÜ',
  'PENDING REVIEW': 'DEĞERLENDİRME BEKLİYOR',
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
  [/^Value (.+) is within reference range \[(.+), (.+)\]\.$/, (_all, value, min, max) => `Değer ${value}, [${min}, ${max}] referans aralığı içindedir.`],
  [/^Value (.+) is above reference maximum (.+)\.$/, (_all, value, max) => `Değer ${value}, ${max} üst referans sınırının üzerindedir.`],
  [/^Value (.+) is below reference minimum (.+)\.$/, (_all, value, min) => `Değer ${value}, ${min} alt referans sınırının altındadır.`],
  [/^(\d+) structured lab result row loaded\.$/, (_all, count) => `${count} laboratuvar sonucu yüklendi.`],
  [/^(\d+) clinical review prompt available\.$/, (_all, count) => `${count} klinik değerlendirme mevcut.`],
  [/^(\d+) result\(s\)$/, (_all, count) => `${count} sonuç`],
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

  return value;
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
