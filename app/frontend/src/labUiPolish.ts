const TEXT_REPLACEMENTS = new Map<string, string>([
  ['Tiroglobulin', 'Globulin'],
  [
    'Belirsiz sonuçlar hekim kontrolü için ayrıldı.',
    'Kaynak raporda güvenilir referans veya sınıflandırma bulunmayan sonuçlar hekim/kaynak doğrulamasına ayrılır.',
  ],
  [
    'Parametre eşleştirmesi, referans aralığı veya sınıflandırma belirsiz.',
    'Kaynak raporda güvenilir referansı bulunmayan veya çıkarımı belirsiz sonuçlar klinik bağlamda doğrulanmalıdır.',
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
