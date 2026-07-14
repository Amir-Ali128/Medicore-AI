const TEXT_REPLACEMENTS = new Map<string, string>([
  ['Tiroglobulin', 'Globulin'],
  ['Hekim Kontrolü Gerekenler', 'Hesaplanan / Özel Parametreler'],
  [
    'Belirsiz sonuçlar hekim kontrolü için ayrıldı.',
    'Sabit referansı olmayan veya klinik bağlama göre yorumlanan sonuçlar.',
  ],
  [
    'Parametre eşleştirmesi, referans aralığı veya sınıflandırma belirsiz.',
    'Hesaplanan, özel veya sabit referansı bulunmayan parametreler klinik bağlama göre değerlendirilir.',
  ],
]);

function polishTextNode(node: Node) {
  if (node.nodeType !== Node.TEXT_NODE || !node.textContent) return;

  const replacement = TEXT_REPLACEMENTS.get(node.textContent.trim());
  if (replacement) {
    node.textContent = node.textContent.replace(node.textContent.trim(), replacement);
  }
}

function polishTree(root: Node) {
  polishTextNode(root);
  root.childNodes.forEach(polishTree);
}

export function installLabUiPolish() {
  const apply = () => polishTree(document.body);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply, { once: true });
  } else {
    apply();
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach(polishTree);
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
}
