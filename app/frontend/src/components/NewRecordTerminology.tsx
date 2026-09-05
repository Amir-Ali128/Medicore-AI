import { useEffect } from 'react';

const EXACT_REPLACEMENTS = new Map<string, string>([
  ['Yeni Hasta Kaydı', 'Yeni Kayıt'],
  ['+ Yeni Hasta Kaydı', '+ Yeni Kayıt'],
  ['Yeni hasta kaydı', 'Yeni kayıt'],
  ['+ Yeni Hasta', '+ Yeni Kayıt'],
  ['Yeni hasta kaydı hazırlanıyor…', 'Yeni kayıt hazırlanıyor…'],
  ['Formu yeni hasta için temizle', 'Formu yeni kayıt için temizle'],
  ['Yeni hastayı kaydet', 'Yeni kaydı oluştur'],
  [
    'İlk hastayı oluşturmak için Yeni Hasta Kaydı düğmesini kullanın.',
    'İlk kaydı oluşturmak için Yeni Kayıt düğmesini kullanın.',
  ],
  ['+ İlk hastayı oluştur', '+ İlk kaydı oluştur'],
]);

function replaceText(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return value;

  const exact = EXACT_REPLACEMENTS.get(trimmed);
  if (exact) return value.replace(trimmed, exact);

  const created = trimmed.match(/^Yeni hasta kaydı oluşturuldu:\s*(.+)$/);
  if (created) {
    return value.replace(trimmed, `Yeni kayıt oluşturuldu: ${created[1]}`);
  }

  return value;
}

function localizeNode(root: Node) {
  if (root.nodeType === Node.TEXT_NODE) {
    const textNode = root as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
      const next = replaceText(textNode.nodeValue ?? '');
      if (next !== textNode.nodeValue) textNode.nodeValue = next;
    }
    return;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current) {
    const textNode = current as Text;
    const parent = textNode.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
      const next = replaceText(textNode.nodeValue ?? '');
      if (next !== textNode.nodeValue) textNode.nodeValue = next;
    }
    current = walker.nextNode();
  }
}

export default function NewRecordTerminology() {
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
