import { useEffect } from 'react';

const REPLACEMENTS: Array<[string, string]> = [
  ['Radyoloji Rapor Analizi', 'Radyoloji ve Tetkik Raporları'],
  ['Radyoloji Raporları', 'Radyoloji ve Tetkik Raporları'],
];

function updateNode(root: Node) {
  const updateText = (node: Text) => {
    let value = node.nodeValue ?? '';

    for (const [source, target] of REPLACEMENTS) {
      value = value.split(source).join(target);
    }

    if (value !== node.nodeValue) node.nodeValue = value;
  };

  if (root.nodeType === Node.TEXT_NODE) {
    updateText(root as Text);
    return;
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();

  while (current) {
    const parent = current.parentElement;
    if (parent && !['SCRIPT', 'STYLE', 'TEXTAREA'].includes(parent.tagName)) {
      updateText(current as Text);
    }
    current = walker.nextNode();
  }
}

export default function RadiologyTerminologyLocalizer() {
  useEffect(() => {
    updateNode(document.body);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          updateNode(mutation.target);
        } else {
          for (const node of mutation.addedNodes) updateNode(node);
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
