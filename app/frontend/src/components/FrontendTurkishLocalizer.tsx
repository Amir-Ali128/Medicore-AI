import { useEffect } from 'react';

const EXACT_TRANSLATIONS: Record<string, string> = {
  'Unknown patient': 'Bilinmeyen hasta',
  'Extracted from uploaded PDF': 'Yüklenen PDF’den çıkarıldı',
  'PDF metadata not available': 'PDF hasta bilgisi bulunamadı',
  'Current workflow': 'Mevcut iş akışı',
  'Latest report status': 'Son rapor durumu',
  'Doctor review pending': 'Hekim değerlendirmesi bekleniyor',
  'Doctor action recorded': 'Hekim işlemi kaydedildi',
  'Analysis ready': 'Analiz hazır',
  'Backend workflow status for latest analysis run.': 'Son analiz çalışmasının iş akışı durumu.',
  'Pending doctor reviews': 'Bekleyen hekim değerlendirmeleri',
  'Clinical review prompts awaiting doctor action.': 'Hekim işlemi bekleyen klinik değerlendirmeler.',
  'Abnormal lab signals': 'Anormal laboratuvar bulguları',
  'LOW or HIGH lab result statuses.': 'Düşük veya yüksek olarak sınıflandırılan laboratuvar sonuçları.',
  'Timeline events': 'Zaman çizelgesi olayları',
  'Backend workflow events in this patient view.': 'Bu hasta görünümündeki iş akışı olayları.',
  'Latest report summary': 'Son rapor özeti',
  'Backend analysis and review status for the latest workflow.': 'Son iş akışının analiz ve değerlendirme durumu.',
  'Report source': 'Rapor kaynağı',
  'Backend lab report': 'Laboratuvar raporu',
  'Latest local workflow': 'Son yerel iş akışı',
  'Latest event': 'Son işlem',
  'Analysis status': 'Analiz durumu',
  'Clinical review prompt status': 'Klinik değerlendirme durumu',
  'Doctor review status': 'Hekim değerlendirme durumu',
  'Patient visibility': 'Hasta görünürlüğü',
  'Patient workflow shortcuts': 'Hasta iş akışı kısayolları',
  'Backend-connected navigation for this patient workspace.': 'Bu hasta çalışma alanına ait bağlantılar.',
  'View analysis results': 'Analiz sonuçlarını görüntüle',
  'Open structured backend lab result rows.': 'Yapılandırılmış laboratuvar sonuçlarını aç.',
  'Clinical review prompts': 'Klinik değerlendirmeler',
  'Create or view generated clinical review prompts.': 'Oluşturulan klinik değerlendirmeleri aç veya yenisini oluştur.',
  'Doctor review': 'Hekim değerlendirmesi',
  'Approve, reject, or request extra tests.': 'Onayla, reddet veya ek test iste.',
  'Doctor worklist': 'Hekim iş listesi',
  'View all backend review tasks.': 'Tüm değerlendirme görevlerini görüntüle.',
  'Lab signal summary': 'Laboratuvar sonuç özeti',
  'Structured lab signal values from backend analysis results.': 'Analiz sonuçlarından elde edilen yapılandırılmış laboratuvar değerleri.',
  'Recent timeline preview': 'Son işlemler',
  'Latest backend workflow events for this patient.': 'Bu hastaya ait son iş akışı olayları.',
  'Analysis run selected': 'Analiz çalışması seçildi',
  'Structured lab results loaded': 'Yapılandırılmış laboratuvar sonuçları yüklendi',
  'Intake': 'Klinik kayıt',
  'Frontend workflow': 'Frontend iş akışı',
  'Lab analysis': 'Laboratuvar analizi',
  'Backend analysis service': 'Backend analiz servisi',
  'Clinical review prompt': 'Klinik değerlendirme',
  'Doctor reviewer': 'Değerlendiren hekim',
  'Doctor review workflow': 'Hekim değerlendirme iş akışı',
  'Clinical review prompts linked to this analysis run.': 'Bu analiz çalışmasına bağlı klinik değerlendirmeler.',
  'Review status breakdown': 'Değerlendirme durumu dağılımı',
  'Doctor review actions recorded for this patient workflow.': 'Bu hasta iş akışına kaydedilen hekim işlemleri.',
  'Pending': 'Bekliyor',
  'Approved': 'Onaylandı',
  'Rejected': 'Reddedildi',
  'Extra test requested': 'Ek test istendi',
  'Latest prompt': 'Son değerlendirme',
  'Severity': 'Şiddet',
  'Confidence': 'Güven',
  'Evidence': 'Kanıt',
  'Safety framing': 'Güvenlik çerçevesi',
  'Patient detail shows workflow state, not medical advice.': 'Hasta detayı tıbbi tavsiye değil, iş akışı durumunu gösterir.',
  'Patient detail events are workflow records, not diagnoses.': 'Hasta detayındaki kayıtlar tanı değil, iş akışı kayıtlarıdır.',
  'Clinical review prompts remain under physician review controls.': 'Klinik değerlendirmeler hekim kontrolünde kalır.',
  'Patient-facing visibility remains blocked until review rules pass.': 'Değerlendirme tamamlanana kadar hasta görünürlüğü kapalı kalır.',
  'Final clinical decisions belong to a physician.': 'Nihai klinik karar hekime aittir.',
  'Backend-connected patient': 'Sisteme bağlı hasta kaydı',
  Name: 'Ad Soyad',
  Age: 'Yaş',
  Sex: 'Cinsiyet',
  'Clinical outputs are structured for physician review and are not a diagnosis.': 'Klinik çıktılar hekim değerlendirmesi için yapılandırılmıştır ve tanı değildir.',
  'Analysis run:': 'Analiz çalışması:',
  'Lab report:': 'Laboratuvar raporu:',
  'Not stored locally': 'Yerel olarak kaydedilmedi',
  'Reference:': 'Referans:',
  NORMAL: 'NORMAL',
  HIGH: 'YÜKSEK',
  LOW: 'DÜŞÜK',
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
  'Analysis summary': 'Analiz özeti',
  'Normal rows are excluded from the visible review queue.': 'Normal sonuçlar görünür değerlendirme listesinin dışında tutulur.',
  'Processed results': 'İşlenen sonuçlar',
  'High signals': 'Yüksek sonuçlar',
  'Low signals': 'Düşük sonuçlar',
  'Needs review': 'Hekim kontrolü gerekenler',
  'All values processed by the deterministic pipeline.': 'Tüm değerler deterministik analiz hattında işlendi.',
  'Above an available reference range.': 'Mevcut referans aralığının üzerinde.',
  'Below an available reference range.': 'Mevcut referans aralığının altında.',
  'Unknown or uncertain results separated for review.': 'Belirsiz sonuçlar hekim kontrolü için ayrıldı.',
};

const REGEX_TRANSLATIONS: Array<[RegExp, (...matches: string[]) => string]> = [
  [/^Value (.+) is within reference range \[(.+), (.+)\]\.$/, (_all, value, min, max) => `Değer ${value}, [${min}, ${max}] referans aralığı içindedir.`],
  [/^Value (.+) is above reference maximum (.+)\.$/, (_all, value, max) => `Değer ${value}, ${max} üst referans sınırının üzerindedir.`],
  [/^Value (.+) is below reference minimum (.+)\.$/, (_all, value, min) => `Değer ${value}, ${min} alt referans sınırının altındadır.`],
  [/^(\d+) structured lab result row loaded\.$/, (_all, count) => `${count} yapılandırılmış laboratuvar sonucu yüklendi.`],
  [/^(\d+) clinical review prompt available\.$/, (_all, count) => `${count} klinik değerlendirme mevcut.`],
  [/^(\d+) structured lab result row loaded\. No abnormal result status is currently marked\.$/, (_all, count) => `${count} yapılandırılmış laboratuvar sonucu yüklendi. Anormal olarak işaretlenen sonuç bulunmuyor.`],
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

function localizeNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const textNode = root as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA', 'OPTION'].includes(parent.tagName)) {
      const translated = translateText(textNode.nodeValue ?? '');
      if (translated !== textNode.nodeValue) textNode.nodeValue = translated;
    }
    return;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    const textNode = current as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA', 'OPTION'].includes(parent.tagName)) {
      const translated = translateText(textNode.nodeValue ?? '');
      if (translated !== textNode.nodeValue) textNode.nodeValue = translated;
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
