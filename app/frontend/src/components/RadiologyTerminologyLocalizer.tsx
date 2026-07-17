import { useEffect } from 'react';

const REPLACEMENTS: Array<[string, string]> = [
  ['Radyoloji Rapor Analizi', 'Radyoloji ve Tetkik Raporları'],
  ['Radyoloji Raporları', 'Radyoloji ve Tetkik Raporları'],
];

const EXTRA_REPORT_TYPES = [
  'Endoskopi raporu',
  'Kolonoskopi raporu',
  'EKG / EKO raporu',
  'EEG / EMG raporu',
  'DEXA raporu',
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

function addExtraReportTypes() {
  const headings = Array.from(document.querySelectorAll('p'));
  const heading = headings.find(
    (element) => element.textContent?.trim() === 'Planlanan rapor türleri',
  );

  const chipContainer = heading?.nextElementSibling;
  if (!(chipContainer instanceof HTMLElement)) return;
  if (chipContainer.dataset.extraReportTypesAdded === 'true') return;

  for (const reportType of EXTRA_REPORT_TYPES) {
    const chip = document.createElement('span');
    chip.className =
      'rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700';
    chip.textContent = reportType;
    chipContainer.appendChild(chip);
  }

  chipContainer.dataset.extraReportTypesAdded = 'true';
}

export default function RadiologyTerminologyLocalizer() {
  useEffect(() => {
    updateNode(document.body);
    addExtraReportTypes();

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === 'characterData') {
          updateNode(mutation.target);
        } else {
          for (const node of mutation.addedNodes) updateNode(node);
        }
      }

      addExtraReportTypes();
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
