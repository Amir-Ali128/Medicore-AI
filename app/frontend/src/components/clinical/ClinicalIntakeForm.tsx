import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ReactNode,
} from 'react';

import type { ClinicalIntakeInput } from '../../services/labAnalysisClient';

export const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';
const CLINICAL_INTAKE_UPDATED_EVENT = 'medicore:clinical-intake-updated';

type ClinicalIntakeFormProps = {
  value: ClinicalIntakeInput;
  onChange: (value: ClinicalIntakeInput) => void;
};

type SectionProps = {
  title: string;
  description: string;
  children: ReactNode;
};

const INPUT_CLASS =
  'mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 placeholder:text-slate-400';
const TEXTAREA_CLASS = `${INPUT_CLASS} resize-y leading-6`;

export function createEmptyClinicalIntake(): ClinicalIntakeInput {
  return {
    patient_information: {
      full_name: null,
      age: null,
      sex: null,
      height_cm: null,
      weight_kg: null,
    },
    presenting_complaint: {
      reason_for_visit: null,
      chief_complaint: null,
      complaint_duration: null,
      severity_score: null,
      associated_symptoms: null,
    },
    clinical_history_details: {
      history_of_present_illness: null,
      current_medical_conditions: null,
      past_medical_history: null,
      family_history: null,
      medications: null,
      allergies: null,
      tobacco_alcohol: null,
      past_surgeries: null,
    },
    physical_exam: {
      blood_pressure_systolic: null,
      blood_pressure_diastolic: null,
      pulse_bpm: null,
      temperature_c: null,
      respiratory_rate: null,
      oxygen_saturation_percent: null,
      examination_findings: null,
    },
    imaging_results: {
      xray: null,
      ultrasound: null,
      ct: null,
      mri: null,
      pet_ct: null,
      pathology: null,
    },
    attachments: [],
  };
}

function normalizeStoredClinicalIntake(raw: unknown): ClinicalIntakeInput | null {
  if (!raw || typeof raw !== 'object') return null;

  const source = raw as Partial<ClinicalIntakeInput>;
  const empty = createEmptyClinicalIntake();
  const patient: Partial<ClinicalIntakeInput['patient_information']> =
    source.patient_information ?? {};

  return {
    patient_information: {
      full_name: null,
      age: patient.age ?? null,
      sex: patient.sex ?? null,
      height_cm: patient.height_cm ?? null,
      weight_kg: patient.weight_kg ?? null,
    },
    presenting_complaint: {
      ...empty.presenting_complaint,
      ...(source.presenting_complaint ?? {}),
    },
    clinical_history_details: {
      ...empty.clinical_history_details,
      ...(source.clinical_history_details ?? {}),
    },
    physical_exam: {
      ...empty.physical_exam,
      ...(source.physical_exam ?? {}),
    },
    imaging_results: {
      ...empty.imaging_results,
      ...(source.imaging_results ?? {}),
    },
    attachments: Array.isArray(source.attachments) ? source.attachments : [],
  };
}

export function readStoredClinicalIntake(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return null;
    return normalizeStoredClinicalIntake(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function persistClinicalIntake(value: ClinicalIntakeInput): void {
  try {
    const sanitizedValue: ClinicalIntakeInput = {
      ...value,
      patient_information: {
        ...value.patient_information,
        full_name: null,
      },
    };
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(sanitizedValue),
    );
    window.dispatchEvent(
      new CustomEvent(CLINICAL_INTAKE_UPDATED_EVENT, { detail: sanitizedValue }),
    );
  } catch {
    // Storage may be unavailable in private/restricted browser contexts.
  }
}

export function clearStoredClinicalIntake(): void {
  try {
    localStorage.removeItem(ACTIVE_CLINICAL_INTAKE_KEY);
  } catch {
    // Storage may be unavailable in private/restricted browser contexts.
  }
}

function FormSection({ title, description, children }: SectionProps) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-lg font-semibold text-slate-950">{title}</h3>
      <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function textOrNull(value: string): string | null {
  return value === '' ? null : value;
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function savedTimeLabel(value: Date | null) {
  if (!value) return 'Henüz değişiklik yapılmadı';
  return `Son kayıt: ${value.toLocaleTimeString('tr-TR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })}`;
}

export default function ClinicalIntakeForm({
  value,
  onChange,
}: ClinicalIntakeFormProps) {
  const hydratedRef = useRef(false);
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;

    const stored = readStoredClinicalIntake();
    if (stored) {
      onChange(stored);
      setSavedAt(new Date());
    }
  }, [onChange]);

  const emitChange = (nextValue: ClinicalIntakeInput) => {
    const sanitizedValue: ClinicalIntakeInput = {
      ...nextValue,
      patient_information: {
        ...nextValue.patient_information,
        full_name: null,
      },
    };
    persistClinicalIntake(sanitizedValue);
    setSavedAt(new Date());
    onChange(sanitizedValue);
  };

  const updatePatient = (
    key: keyof ClinicalIntakeInput['patient_information'],
    fieldValue: string | number | null,
  ) => {
    emitChange({
      ...value,
      patient_information: {
        ...value.patient_information,
        [key]: fieldValue,
      },
    });
  };

  const updateComplaint = (fieldValue: string | null) => {
    emitChange({
      ...value,
      presenting_complaint: {
        ...value.presenting_complaint,
        chief_complaint: fieldValue,
      },
    });
  };

  const updateHistory = (
    key: keyof ClinicalIntakeInput['clinical_history_details'],
    fieldValue: string | null,
  ) => {
    emitChange({
      ...value,
      clinical_history_details: {
        ...value.clinical_history_details,
        [key]: fieldValue,
      },
    });
  };

  const updateExam = (
    key: keyof ClinicalIntakeInput['physical_exam'],
    fieldValue: string | number | null,
  ) => {
    emitChange({
      ...value,
      physical_exam: {
        ...value.physical_exam,
        [key]: fieldValue,
      },
    });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-emerald-950">
            Klinik bilgiler otomatik kaydedilir
          </p>
          <p className="mt-1 text-xs leading-5 text-emerald-800">
            Girdiğiniz bilgiler bu tarayıcıda korunur ve diğer değerlendirme ekranlarında kullanılabilir.
          </p>
        </div>
        <div className="shrink-0 text-xs font-semibold text-emerald-800">
          {savedTimeLabel(savedAt)}
        </div>
      </div>

      <FormSection
        title="Temel bilgiler"
        description="Klinik değerlendirme için gerekli temel bilgiler."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <label className="text-sm font-medium text-slate-700">
            Yaş
            <input
              type="number"
              min={0}
              max={130}
              value={value.patient_information.age ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                updatePatient('age', numberOrNull(event.target.value))
              }
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Cinsiyet
            <select
              value={value.patient_information.sex ?? ''}
              onChange={(event: ChangeEvent<HTMLSelectElement>) =>
                updatePatient('sex', textOrNull(event.target.value))
              }
              className={INPUT_CLASS}
            >
              <option value="">Seçiniz</option>
              <option value="male">Erkek</option>
              <option value="female">Kadın</option>
              <option value="other">Diğer</option>
              <option value="unknown">Bilinmiyor</option>
            </select>
          </label>

          <label className="text-sm font-medium text-slate-700">
            Kilo (kg)
            <input
              type="number"
              min={1}
              max={600}
              step="0.1"
              value={value.patient_information.weight_kg ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                updatePatient('weight_kg', numberOrNull(event.target.value))
              }
              className={INPUT_CLASS}
            />
          </label>
        </div>
      </FormSection>

      <FormSection
        title="Şikâyet ve belirtiler"
        description="Başvuru şikâyetini ve eşlik eden belirtileri tek alanda yazın."
      >
        <textarea
          rows={5}
          value={value.presenting_complaint.chief_complaint ?? ''}
          onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
            updateComplaint(textOrNull(event.target.value))
          }
          placeholder="Şikâyet, belirtiler, süresi ve önemli ayrıntılar"
          className={TEXTAREA_CLASS}
        />
      </FormSection>

      <FormSection
        title="Tıbbi öykü"
        description="Mevcut hastalıklar, geçmiş sağlık bilgileri, ilaçlar ve risk faktörleri."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {[
            ['current_medical_conditions', 'Mevcut hastalıklar', 'Hâlen takip edilen hastalıklar ve önemli tanılar'],
            ['past_medical_history', 'Geçmiş sağlık öyküsü', 'Önceki hastalıklar, yatışlar ve önemli sağlık olayları'],
            ['family_history', 'Aile öyküsü', 'Ailede görülen önemli veya kalıtsal hastalıklar'],
            ['medications', 'Kullanılan ilaçlar', 'İlaç adı, doz ve kullanım sıklığı'],
            ['allergies', 'Alerjiler', 'Bilinen alerjiler ve oluşan reaksiyonlar'],
            ['tobacco_alcohol', 'Sigara ve alkol kullanımı', 'Miktar, sıklık ve kullanım süresi'],
            ['past_surgeries', 'Geçirilmiş ameliyatlar', 'Ameliyat türü, tarihi ve varsa komplikasyonlar'],
          ].map(([key, label, placeholder]) => (
            <label key={key} className="text-sm font-medium text-slate-700">
              {label}
              <textarea
                rows={3}
                value={
                  value.clinical_history_details[
                    key as keyof ClinicalIntakeInput['clinical_history_details']
                  ] ?? ''
                }
                onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                  updateHistory(
                    key as keyof ClinicalIntakeInput['clinical_history_details'],
                    textOrNull(event.target.value),
                  )
                }
                placeholder={placeholder}
                className={TEXTAREA_CLASS}
              />
            </label>
          ))}
        </div>
      </FormSection>

      <FormSection
        title="Muayene ve yaşamsal bulgular"
        description="Ölçülen yaşamsal bulgular ve muayene notları."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {[
            ['blood_pressure_systolic', 'Sistolik tansiyon', 'mmHg', 40, 300],
            ['blood_pressure_diastolic', 'Diyastolik tansiyon', 'mmHg', 20, 200],
            ['pulse_bpm', 'Nabız', '/dk', 20, 300],
            ['temperature_c', 'Vücut sıcaklığı', '°C', 30, 45],
            ['respiratory_rate', 'Solunum sayısı', '/dk', 4, 80],
            ['oxygen_saturation_percent', 'Oksijen satürasyonu', '%', 0, 100],
          ].map(([key, label, placeholder, min, max]) => (
            <label key={String(key)} className="text-sm font-medium text-slate-700">
              {label}
              <input
                type="number"
                min={Number(min)}
                max={Number(max)}
                step={
                  key === 'temperature_c' || key === 'oxygen_saturation_percent'
                    ? '0.1'
                    : '1'
                }
                value={
                  value.physical_exam[
                    key as keyof ClinicalIntakeInput['physical_exam']
                  ] ?? ''
                }
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  updateExam(
                    key as keyof ClinicalIntakeInput['physical_exam'],
                    numberOrNull(event.target.value),
                  )
                }
                placeholder={String(placeholder)}
                className={INPUT_CLASS}
              />
            </label>
          ))}

          <label className="text-sm font-medium text-slate-700 sm:col-span-2 lg:col-span-3 xl:col-span-6">
            Muayene bulguları
            <textarea
              rows={4}
              value={value.physical_exam.examination_findings ?? ''}
              onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                updateExam('examination_findings', textOrNull(event.target.value))
              }
              placeholder="Genel durum ve sistem muayenesinde saptanan önemli bulgular"
              className={TEXTAREA_CLASS}
            />
          </label>
        </div>
      </FormSection>
    </div>
  );
}
