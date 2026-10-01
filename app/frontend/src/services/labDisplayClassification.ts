import type { LabInput } from './simpleCaseClient';

export type LabDisplayClassification = {
  status: 'normal' | 'abnormal' | 'unclassified';
  direction: 'low' | 'high' | null;
};
const unknown: LabDisplayClassification = { status: 'unclassified', direction: null };

function numeric(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string' || !/^-?\d+(?:[.,]\d+)?$/.test(value.trim())) return null;
  const result = Number(value.trim().replace(',', '.'));
  return Number.isFinite(result) ? result : null;
}

export function classifyLabForDisplay(lab: LabInput): LabDisplayClassification {
  const reasons = lab.source_metadata?.ingestion_reasons;
  if (Array.isArray(reasons) && reasons.some((r) => /conflict|missing_parameter|missing_observed|invalid_reference|numeric_value_conflict|reference_unit_mismatch|invalid_numeric|low_input_confidence/.test(String(r)))) return unknown;
  // Copy explicit printed flags; never trust stale computed display metadata.
  const flag = String(lab.source_metadata?.source_flag ?? '').toLocaleLowerCase('tr-TR').trim();
  if (['yüksek', 'high', 'h', '↑'].includes(flag)) return { status: 'abnormal', direction: 'high' };
  if (['düşük', 'low', 'l', '↓'].includes(flag)) return { status: 'abnormal', direction: 'low' };
  if (['normal', 'n'].includes(flag)) return { status: 'normal', direction: null };

  const match = String(lab.value ?? '').trim().replace(',', '.').match(/^([<>]=?)?\s*(-?\d+(?:\.\d+)?)$/);
  if (!match) return unknown;
  const value = numeric(match[2]);
  if (value === null) return unknown;
  const comparator = match[1] ?? null;
  const refs = lab.source_references ?? [];
  // Context-specific intervals need clinical age/sex selection; do not guess in UI.
  if (refs.some((r) => r.age_min != null || r.age_max != null || (r.sex && r.sex !== 'unknown'))) return unknown;
  const ref = refs[0];
  if (ref?.unit && lab.unit && ref.unit.trim().toLowerCase() !== lab.unit.trim().toLowerCase()) return unknown;
  const text = (lab.source_reference ?? ref?.text ?? '').trim().replace(/,/g, '.');
  const range = text.match(/^(-?\d+(?:\.\d+)?)\s*[-–—]\s*(-?\d+(?:\.\d+)?)(?:\s+([^\s]+))?$/);
  const one = text.match(/^([<>]=?)\s*(-?\d+(?:\.\d+)?)(?:\s+([^\s]+))?$/);
  const textUnit = range?.[3] ?? one?.[3];
  if (textUnit && lab.unit && textUnit.toLowerCase() !== lab.unit.trim().toLowerCase()) return unknown;
  if (text && !range && !one) return unknown;
  let minimum = numeric(ref?.minimum);
  let maximum = numeric(ref?.maximum);
  if (range) {
    const lo = numeric(range[1]), hi = numeric(range[2]);
    if ((minimum !== null && minimum !== lo) || (maximum !== null && maximum !== hi)) return unknown;
    minimum = lo; maximum = hi;
  } else if (one) {
    const limit = numeric(one[2]);
    if (one[1].startsWith('<')) maximum = limit;
    else minimum = limit;
  }
  if ((minimum === null && maximum === null) || (minimum !== null && maximum !== null && minimum > maximum)) return unknown;
  const lowerStrict = one?.[1] === '>';
  const upperStrict = one?.[1] === '<';
  if (!comparator) {
    if (minimum !== null && (value < minimum || (lowerStrict && value === minimum))) return { status: 'abnormal', direction: 'low' };
    if (maximum !== null && (value > maximum || (upperStrict && value === maximum))) return { status: 'abnormal', direction: 'high' };
    return { status: 'normal', direction: null };
  }
  // A bound is classifiable only when every possible censored value agrees.
  if (comparator.startsWith('<')) {
    if (minimum !== null && (value < minimum || (value === minimum && (comparator === '<' || lowerStrict)))) return { status: 'abnormal', direction: 'low' };
    if (minimum === null && maximum !== null && (value < maximum || (value === maximum && (!upperStrict || comparator === '<')))) return { status: 'normal', direction: null };
  } else {
    if (maximum !== null && (value > maximum || (value === maximum && (comparator === '>' || upperStrict)))) return { status: 'abnormal', direction: 'high' };
    if (maximum === null && minimum !== null && (value > minimum || (value === minimum && (!lowerStrict || comparator === '>')))) return { status: 'normal', direction: null };
  }
  return unknown;
}
