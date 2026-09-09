import { useEffect } from 'react';

const EXACT_TEXT: Record<string, string> = {
  'Klinik Karar Desteği': 'MediCore AI',
  'Klinik ve laboratuvar değerlendirmesi': 'Laboratuvar Sonuçları',
  'Laboratuvar değerlendirmesi': 'Sonuçlar',
  'Klinik bilgiler': 'Hasta Bilgileri',
  'Yapay Zekâ Laboratuvar Analizi': 'Laboratuvar Sonuçları',
  'Yapay Zekâ Destekli Klinik Değerlendirme': 'AI Yorumu',
  'Klinik Değerlendirme': 'AI Yorumu',
  'Klinik değerlendirme': 'AI yorumu',
  'Klinik Değerlendirmeler': 'AI Yorumları',
  'Klinik değerlendirmeler': 'AI yorumları',
  'Klinik değerlendirme durumu': 'AI durumu',
  'Klinik Değerlendirmeleri Aç': 'AI Yorumunu Aç',
  'Dayanak bulgular': 'Önemli Bulgular',
  'Dayanak Bulgular': 'Önemli Bulgular',
  'Değerlendirme notu': 'Açıklama',
  'Clinical Brain': 'AI',
  'Python Clinical Brain': 'AI',
  'Clinical Engine': 'AI',
  'Clinical Fusion': 'AI',
  'Clinical Fusion Brain': 'AI',
  'Clinical Fusion Engine': 'AI',
  'Clinical decision support': 'AI destekli değerlendirme',
  'Backend analysis service': 'Analiz',
  'Frontend workflow': 'İşlem',
  'Model output': 'AI Sonucu',
  'System output': 'AI Sonucu',
};

const REPLACEMENTS: Array<[RegExp, string]> = [
  [/Python Clinical Brain/gi, 'AI'],
  [/Clinical Fusion Brain/gi, 'AI'],
  [/Clinical Fusion Engine/gi, 'AI'],
  [/Clinical Decision Support Engine/gi, 'AI'],
  [/Clinical Engine/gi, 'AI'],
  [/Clinical Brain/gi, 'AI'],
  [/C\+\+\s*(?:Lab|Clinical|Vision)?\s*(?:Engine|Motoru)/gi, 'AI'],
  [/Yapay Zekâ Destekli Klinik Değerlendirme/gi, 'AI Yorumu'],
  [/Yapay Zekâ Laboratuvar Analizi/gi, 'Laboratuvar Sonuçları'],
  [/Klinik ve laboratuvar değerlendirmesi/gi, 'Laboratuvar Sonuçları'],
  [/Klinik Karar Desteği/gi, 'MediCore AI'],
  [/Klinik değerlendirme durumu/gi, 'AI durumu'],
  [/Klinik Değerlendirmeleri/gi, 'AI Yorumlarını'],
  [/Klinik Değerlendirmeler/gi, 'AI Yorumları'],
  [/Klinik değerlendirmeleri/gi, 'AI yorumlarını'],
  [/Klinik değerlendirmeler/gi, 'AI yorumları'],
  [/Klinik Değerlendirme/gi, 'AI Yorumu'],
  [/Klinik değerlendirme/gi, 'AI yorumu'],
  [/Laboratuvar değerlendirmesi/gi, 'Sonuçlar'],
  [/Klinik bilgiler/gi, 'Hasta Bilgileri'],
  [/Dayanak bulgular/gi, 'Önemli Bulgular'],
  [/Backend analysis service/gi, 'Analiz'],
  [/Frontend workflow/gi, 'İşlem'],
  [/\bBackend\b/gi, 'Sistem'],
  [/\bFrontend\b/gi, 'Arayüz'],
  [/\bPipeline\b/gi, 'İşlem'],
  [/\bWorkflow\b/gi, 'İşlem'],
  [/\bModel output\b/gi, 'AI Sonucu'],
  [/\bSystem output\b/gi, 'AI Sonucu'],
];

function simplifyText(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return value;

  const exact = EXACT_TEXT[trimmed];
  if (exact) return value.replace(trimmed, exact);

  let simplified = value;
  for (const [pattern, replacement] of REPLACEMENTS) {
    simplified = simplified.replace(pattern, replacement);
  }
  return simplified;
}

function simplifyElementAttributes(element: Element) {
  for (const attributeName of ['placeholder', 'title', 'aria-label']) {
    const current = element.getAttribute(attributeName);
    if (!current) continue;
    const simplified = simplifyText(current);
    if (simplified !== current) element.setAttribute(attributeName, simplified);
  }
}

function simplifyNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const textNode = root as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName)) {
      const current = textNode.nodeValue ?? '';
      const simplified = simplifyText(current);
      if (simplified !== current) textNode.nodeValue = simplified;
    }
    return;
  }

  if (root instanceof Element) simplifyElementAttributes(root);

  const walker = document.createTreeWalker(
    root,
    NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
  );

  let current = walker.nextNode();
  while (current) {
    if (current.nodeType === Node.ELEMENT_NODE) {
      simplifyElementAttributes(current as Element);
    } else {
      const textNode = current as Text;
      const parent = textNode.parentElement;
      if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE'].includes(parent.tagName)) {
        const currentValue = textNode.nodeValue ?? '';
        const simplified = simplifyText(currentValue);
        if (simplified !== currentValue) textNode.nodeValue = simplified;
      }
    }
    current = walker.nextNode();
  }
}

export default function UserFacingTerminologySimplifier() {
  useEffect(() => {
    simplifyNode(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          simplifyNode(mutation.target);
          continue;
        }

        for (const node of mutation.addedNodes) simplifyNode(node);
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
