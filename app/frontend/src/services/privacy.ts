import type { ClinicalIntakeInput } from './labAnalysisClient';

export function shouldMaskPatientIdentifiers() {
  return (
    import.meta.env.DEV ||
    String(import.meta.env.VITE_MASK_PATIENT_IDENTIFIERS ?? '').toLowerCase() === 'true'
  );
}

export function maskPersonName(value: string | null | undefined) {
  const text = value?.trim();
  if (!text) return value ?? '';
  if (!shouldMaskPatientIdentifiers()) return text;

  return text
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const chars = Array.from(part);
      if (chars.length <= 1) return '*';
      return `${chars[0]}${'*'.repeat(Math.min(Math.max(chars.length - 1, 2), 6))}`;
    })
    .join(' ');
}

export function maskIdentifier(value: string | null | undefined) {
  const text = value?.trim();
  if (!text) return value ?? '';
  if (!shouldMaskPatientIdentifiers()) return text;
  if (text.length <= 4) return '*'.repeat(text.length);
  return `${text.slice(0, 2)}${'*'.repeat(Math.min(text.length - 4, 8))}${text.slice(-2)}`;
}

function safeAttachmentName(index: number, original: string) {
  const extensionMatch = original.match(/\.([A-Za-z0-9]{1,8})$/);
  const extension = extensionMatch ? `.${extensionMatch[1].toLowerCase()}` : '';
  return `clinical-attachment-${index + 1}${extension}`;
}

/**
 * Direct identifiers are not required by the decision-support engines. Keep coarse
 * demographics, symptoms and clinical facts, but remove the name and user supplied
 * attachment filenames before report metadata is persisted.
 */
export function sanitizeClinicalContextForStorage(
  context: ClinicalIntakeInput,
): ClinicalIntakeInput {
  return {
    ...context,
    patient_information: {
      ...context.patient_information,
      full_name: null,
    },
    attachments: context.attachments.map((attachment, index) => ({
      ...attachment,
      file_name: safeAttachmentName(index, attachment.file_name),
    })),
  };
}
