import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

function normalizedText(element: Element) {
  return (element.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function removeAssociatedSymptomsField() {
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {
    const text = normalizedText(label);
    if (text.startsWith('Eşlik eden belirtiler')) {
      label.remove();
    }
  }
}

function removeRadiologyHistory() {
  const headings = Array.from(document.querySelectorAll('h1, h2, h3, p'));
  const title = headings.find((element) => normalizedText(element) === 'Görüntüleme geçmişi');
  if (!title) return;

  const card = title.closest('section') ?? title.parentElement?.parentElement?.parentElement;
  card?.remove();
}

function activateRequestedEntry(pathname: string, search: string) {
  const entry = new URLSearchParams(search).get('entry');
  if (!entry) return;

  window.setTimeout(() => {
    if (pathname === '/radiology') {
      const targetLabel = entry === 'pdf' ? 'PDF yükle' : 'Rapor metni';
      const button = Array.from(document.querySelectorAll('button')).find(
        (element) => normalizedText(element) === targetLabel,
      );
      if (button instanceof HTMLButtonElement) {
        button.click();
        button.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return;
    }

    if (pathname === '/analysis/mock') {
      const targetText = entry === 'pdf'
        ? 'Laboratuvar PDF’si yükle ve analiz et'
        : 'Laboratuvar sonuçlarını manuel gir';
      const target = Array.from(document.querySelectorAll('h2, h3')).find(
        (element) => normalizedText(element) === targetText,
      );
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, 150);
}

export default function WorkflowViewSimplifier() {
  const location = useLocation();

  useEffect(() => {
    const apply = () => {
      removeAssociatedSymptomsField();
      if (location.pathname === '/radiology') removeRadiologyHistory();
    };

    apply();
    activateRequestedEntry(location.pathname, location.search);

    const observer = new MutationObserver(apply);
    observer.observe(document.body, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, [location.pathname, location.search]);

  return null;
}
