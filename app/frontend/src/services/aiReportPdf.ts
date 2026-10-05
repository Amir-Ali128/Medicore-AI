import { Lexer, type Token, type Tokens } from 'marked';
import type { Content, ContentText, Style, TDocumentDefinitions } from 'pdfmake/interfaces';

export const AI_REPORT_DISCLAIMER = 'Bu çıktı klinik karar desteği amacıyla oluşturulmuştur ve hekim değerlendirmesi ile doğrulanmalıdır.';
export const PDF_EXPORT_ERROR = 'PDF oluşturulamadı veya indirilemedi. Lütfen yeniden deneyin; mevcut AI raporunuz korunuyor.';

export type AIReportPdfInput = {
  reportText: string;
  caseId?: string | null;
  protocolNo?: string | null;
  reportWarning?: string;
  createdAt?: Date;
};

const clinicalHeadings = new Set([
  'KLİNİK ÖZET', 'ÖNE ÇIKAN LABORATUVAR BULGULARI', 'TETKİK / RAPOR BULGULARI',
  'ENTEGRE KLİNİK DEĞERLENDİRME', 'OLASI KLİNİK DURUMLAR / AYIRICI TANI',
  'ÖNERİLEN İLERİ TETKİK / İZLEM', 'SONUÇ / KANAAT', 'HEKİM NOTU',
  'KLİNİK BİLGİ', 'LABORATUVAR DEĞERLENDİRMESİ',
]);

function textRun(text: string, style: Style = {}): ContentText {
  return { text, ...style, ...(/\S{40,}/u.test(text) ? { wordBreak: 'break-all' as const } : {}) };
}

function inline(tokens: Token[], style: Style = {}): ContentText[] {
  return tokens.flatMap((token): ContentText[] => {
    switch (token.type) {
      case 'strong': return inline(token.tokens ?? [], { ...style, bold: true });
      case 'em': return inline(token.tokens ?? [], { ...style, italics: true });
      case 'del': return inline(token.tokens ?? [], { ...style, decoration: 'lineThrough' });
      case 'br': return [textRun('\n', style)];
      case 'link': {
        const link = token as Tokens.Link;
        return [...inline(link.tokens, style), ...(link.text !== link.href ? [textRun(` (${link.href})`, style)] : [])];
      }
      // Never fetch remote images or execute embedded HTML in an AI report.
      case 'image': return [textRun(token.raw, style)];
      default: return [textRun('text' in token && typeof token.text === 'string' ? token.text : token.raw, style)];
    }
  });
}

function heading(text: string, depth = 2): Content {
  return { text: inline(Lexer.lexInline(text)), bold: true, fontSize: depth === 1 ? 16 : 13,
    color: '#153c70', margin: [0, 12, 0, 6], headlineLevel: depth };
}

function blocks(tokens: Token[]): Content[] {
  return tokens.flatMap((token): Content[] => {
    switch (token.type) {
      case 'space': case 'def': return [];
      case 'heading': return [heading(token.text, token.depth)];
      case 'paragraph': case 'text': {
        // The current clinical writer emits standalone uppercase headings,
        // sometimes without a blank line before their paragraph.
        const lines = String(token.text).split('\n');
        if (lines.some((line) => clinicalHeadings.has(line.trim().replace(/:$/, '')))) {
          const result: Content[] = [];
          let paragraph: string[] = [];
          const flush = () => { if (paragraph.length) result.push({ text: inline(Lexer.lexInline(paragraph.join('\n'))), margin: [0, 0, 0, 7] }); paragraph = []; };
          for (const line of lines) {
            if (clinicalHeadings.has(line.trim().replace(/:$/, ''))) { flush(); result.push(heading(line)); }
            else paragraph.push(line);
          }
          flush();
          return result;
        }
        return [{ text: inline(token.tokens ?? Lexer.lexInline(String(token.text))), margin: [0, 0, 0, 7] }];
      }
      case 'list': {
        const list = token as Tokens.List;
        const items: Content[] = list.items.map((item) => ({ stack: [
          ...(item.task ? [textRun(item.checked ? '[x] ' : '[ ] ')] : []), ...blocks(item.tokens),
        ] }));
        return [list.ordered ? { ol: items, start: Number(list.start), margin: [0, 0, 0, 8] }
          : { ul: items, margin: [0, 0, 0, 8] }];
      }
      case 'table': {
        const table = token as Tokens.Table;
        const cols = table.header.length;
        const cell = (item: Tokens.TableCell, index: number, bold: boolean): ContentText => ({
          text: inline(item.tokens), bold, alignment: table.align[index] ?? 'left',
          wordBreak: 'break-all', fillColor: bold ? '#eef3f9' : undefined,
        });
        return [{ table: { headerRows: 1, widths: Array(cols).fill('*'),
          body: [table.header.map((item, index) => cell(item, index, true)),
            ...table.rows.map((row) => row.map((item, index) => cell(item, index, false)))],
        }, fontSize: Math.max(6, Math.min(10, 72 / cols)), margin: [0, 5, 0, 10],
        layout: { paddingLeft: () => Math.min(4, 500 / (cols * 8)), paddingRight: () => Math.min(4, 500 / (cols * 8)),
          hLineColor: () => '#ccd5e0', vLineColor: () => '#ccd5e0' } }];
      }
      case 'blockquote': return [{ stack: blocks(token.tokens ?? []), margin: [12, 4, 0, 8], color: '#475569' }];
      case 'code': return [{ ...textRun(token.text), margin: [0, 4, 0, 8], fillColor: '#f5f7fa', fontSize: 10 }];
      case 'hr': return [{ canvas: [{ type: 'line', x1: 0, y1: 0, x2: 499, y2: 0, lineColor: '#ccd5e0' }], margin: [0, 6, 0, 6] }];
      default: return [{ ...textRun(token.raw), margin: [0, 0, 0, 7] }];
    }
  });
}

function exportDay(date: Date) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
  const part = (type: string) => parts.find((value) => value.type === type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function aiReportPdfFilename(input: AIReportPdfInput): string {
  const label = (input.protocolNo?.trim() || input.caseId?.trim() || 'Vaka')
    .replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 80) || 'Vaka';
  return `MediCore_AI_Report_${label}_${exportDay(input.createdAt ?? new Date())}.pdf`;
}

export function buildAIReportPdfDefinition(input: AIReportPdfInput): TDocumentDefinitions {
  if (!input.reportText.trim()) throw new Error('AI raporu henüz oluşturulmadı.');
  const createdAt = input.createdAt ?? new Date();
  const date = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', dateStyle: 'long', timeStyle: 'short' }).format(createdAt);
  return {
    pageSize: 'A4', pageMargins: [48, 48, 48, 48],
    defaultStyle: { font: 'Roboto', fontSize: 11, lineHeight: 1.25 },
    info: { title: 'MediCore AI Raporu', author: 'MediCore', creationDate: createdAt },
    content: [
      { text: 'MediCore Klinik Değerlendirme Raporu', bold: true, fontSize: 18, margin: [0, 0, 0, 8] },
      ...(input.caseId ? [textRun(`Vaka ID: ${input.caseId}`)] : []),
      ...(input.protocolNo ? [textRun(`Protokol / Hasta No: ${input.protocolNo}`)] : []),
      { text: `PDF oluşturulma tarihi: ${date}`, fontSize: 9, color: '#64748b', margin: [0, 4, 0, 12] },
      ...(input.reportWarning ? [{ text: [textRun('AI rapor durumu: ', { bold: true }), textRun(input.reportWarning)], color: '#92400e', margin: [0, 0, 0, 12] as [number, number, number, number] }] : []),
      ...blocks(Lexer.lex(input.reportText, { gfm: true })),
      { text: AI_REPORT_DISCLAIMER, fontSize: 9, color: '#64748b', margin: [0, 16, 0, 0] },
    ],
    footer: (page, pages) => ({ text: `${page} / ${pages}`, alignment: 'center', fontSize: 9, color: '#64748b', margin: [0, 16, 0, 0] }),
    pageBreakBefore: (node, container) => Boolean(node.headlineLevel && !container.getFollowingNodesOnPage().length),
  };
}

export async function createAIReportPdfBlob(input: AIReportPdfInput): Promise<Blob> {
  const definition = buildAIReportPdfDefinition(input);
  // Fonts are embedded in the application bundle; report content never leaves
  // the browser and no provider/backend call is used for export.
  const [pdfMake, fonts] = await Promise.all([import('pdfmake/build/pdfmake.js'), import('pdfmake/build/vfs_fonts.js')]);
  pdfMake.default.addVirtualFileSystem(fonts.default);
  return pdfMake.default.createPdf(definition).getBlob();
}

function savePdfBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  try {
    link.href = url; link.download = filename;
    document.body.appendChild(link); link.click();
  } finally {
    link.remove();
    // Browsers need time to start consuming the URL before revocation.
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
}

export async function exportCurrentAIReport(input: AIReportPdfInput, options: {
  isCurrent?: () => boolean;
  createBlob?: typeof createAIReportPdfBlob;
  saveBlob?: (blob: Blob, filename: string) => void;
} = {}): Promise<boolean> {
  if (!input.reportText.trim()) throw new Error('AI raporu henüz oluşturulmadı.');
  if (options.isCurrent && !options.isCurrent()) return false;
  const snapshot = { ...input, createdAt: input.createdAt ?? new Date() };
  const blob = await (options.createBlob ?? createAIReportPdfBlob)(snapshot);
  // Switching patients or changing the displayed report during generation must
  // not download an earlier patient's document.
  if (options.isCurrent && !options.isCurrent()) return false;
  (options.saveBlob ?? savePdfBlob)(blob, aiReportPdfFilename(snapshot));
  return true;
}
