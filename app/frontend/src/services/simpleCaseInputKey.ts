import type { SimpleCaseRequest } from './simpleCaseClient';

export function simpleCaseInputKey(
  patientId: string | null,
  payload: SimpleCaseRequest,
): string {
  // PostgreSQL JSONB may return object fields in a different order.
  return JSON.stringify({ patientId, payload }, (_key, value) => {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]]));
    }
    return value;
  });
}
