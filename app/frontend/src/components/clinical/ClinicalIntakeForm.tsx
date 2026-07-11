import type { ChangeEvent, ReactNode } from 'react';

import type {
  ClinicalAttachmentCategory,
  ClinicalAttachmentInput,
  ClinicalIntakeInput,
} from '../../services/labAnalysisClient';

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

function FormSection({ title, description, children }: SectionProps) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <div>
        <h3 className="text-lg font-semibold text-slate-950">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-500">{description}</p>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function numberOrNull(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function attachmentMetadata(
  file: File,
  category: ClinicalAttachmentCategory,
): ClinicalAttachmentInput {
  return {
    file_name: file.name,
    category,
    content_type: file.type || null,
    size_bytes: file.size,
    last_modified_ms: Number.isFinite(file.lastModified)
      ? file.lastModified
      : null,
  };
}

function replaceAttachmentGroup(
  current: ClinicalAttachmentInput[],
  files: FileList | null,
  categoriesToReplace: ClinicalAttachmentCategory[],
  targetCategory: ClinicalAttachmentCategory,
): ClinicalAttachmentInput[] {
  const retained = current.filter(
    (item) => !categoriesToReplace.includes(item.category),
  );
  const added = Array.from(files ?? []).map((file) =>
    attachmentMetadata(file, targetCategory),
  );
  return [...retained, ...added];
}

function AttachmentList({
  items,
  emptyText,
}: {
  items: ClinicalAttachmentInput[];
  emptyText: string;
}) {
  if (items.length === 0) {
    return <p className="mt-2 text-xs text-slate-400">{emptyText}</p>;
  }

  return (
    <ul className="mt-3 space-y-2">
      {items.map((item, index) => (
        <li
          key={`${item.category}-${item.file_name}-${index}`}
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600"
        >
          <span className="font-medium text-slate-800">{item.file_name}</span>
          <span>{Math.max(1, Math.round(item.size_bytes / 1024))} KB</span>
        </li>
      ))}
    </ul>
  );
}

export default function ClinicalIntakeForm({
  value,
  onChange,
}: ClinicalIntakeFormProps) {
  const updatePatient = (
    key: keyof ClinicalIntakeInput['patient_information'],
    fieldValue: string | number | null,
  ) => {
    onChange({
      ...value,
      patient_information: {
        ...value.patient_information,
        [key]: fieldValue,
      },
    });
  };

  const updateComplaint = (
    key: keyof ClinicalIntakeInput['presenting_complaint'],
    fieldValue: string | number | null,
  ) => {
    onChange({
      ...value,
      presenting_complaint: {
        ...value.presenting_complaint,
        [key]: fieldValue,
      },
    });
  };

  const updateHistory = (
    key: keyof ClinicalIntakeInput['clinical_history_details'],
    fieldValue: string | null,
  ) => {
    onChange({
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
    onChange({
      ...value,
      physical_exam: {
        ...value.physical_exam,
        [key]: fieldValue,
      },
    });
  };

  const updateImaging = (
    key: keyof ClinicalIntakeInput['imaging_results'],
    fieldValue: string | null,
  ) => {
    onChange({
      ...value,
      imaging_results: {
        ...value.imaging_results,
        [key]: fieldValue,
      },
    });
  };

  const labAttachments = value.attachments.filter(
    (item) => item.category === 'laboratory',
  );
  const imagingAttachments = value.attachments.filter(
    (item) => item.category !== 'laboratory',
  );

  return (
    <div className="space-y-5">
      <FormSection
        title="Hasta Bilgileri"
        description="Kimlik, demografik ve temel antropometrik bilgiler."
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <label className="text-sm font-medium text-slate-700 md:col-span-2">
            Ad Soyad
            <input
              value={value.patient_information.full_name ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updatePatient('full_name', textOrNull(event.target.value))
              }
              maxLength={200}
              placeholder="Hasta adı ve soyadı"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Yaş
            <input
              type="number"
              min={0}
              max={130}
              value={value.patient_information.age ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updatePatient('age', numberOrNull(event.target.value))
              }
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Cinsiyet
            <select
              value={value.patient_information.sex ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
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

          <div className="grid grid-cols-2 gap-3 md:col-span-2 xl:col-span-1">
            <label className="text-sm font-medium text-slate-700">
              Boy (cm)
              <input
                type="number"
                min={30}
                max={260}
                step="0.1"
                value={value.patient_information.height_cm ?? ''}
                onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                  updatePatient('height_cm', numberOrNull(event.target.value))
                }
                className={INPUT_CLASS}
              />
            </label>
            <label className="text-sm font-medium text-slate-700">
              Kilo (kg)
              <input
                type="number"
                min={1}
                max={600}
                step="0.1"
                value={value.patient_information.weight_kg ?? ''}
                onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                  updatePatient('weight_kg', numberOrNull(event.target.value))
                }
                className={INPUT_CLASS}
              />
            </label>
          </div>
        </div>
      </FormSection>

      <FormSection
        title="Başvuru Nedeni"
        description="Ana şikayet, süresi, şiddeti ve eşlik eden belirtiler."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          <label className="text-sm font-medium text-slate-700">
            Başvuru Nedeni
            <textarea
              rows={3}
              value={value.presenting_complaint.reason_for_visit ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateComplaint(
                  'reason_for_visit',
                  textOrNull(event.target.value),
                )
              }
              placeholder="Hastanın sağlık kuruluşuna başvuru nedeni..."
              className={TEXTAREA_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Ana şikayet
            <textarea
              rows={3}
              value={value.presenting_complaint.chief_complaint ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateComplaint(
                  'chief_complaint',
                  textOrNull(event.target.value),
                )
              }
              placeholder="Örn: Halsizlik, baş dönmesi ve çabuk yorulma..."
              className={TEXTAREA_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Şikayetin süresi
            <input
              value={value.presenting_complaint.complaint_duration ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateComplaint(
                  'complaint_duration',
                  textOrNull(event.target.value),
                )
              }
              placeholder="Örn: 3 gündür, 2 aydır, aralıklı..."
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Şiddeti (0-10)
            <input
              type="number"
              min={0}
              max={10}
              value={value.presenting_complaint.severity_score ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateComplaint(
                  'severity_score',
                  numberOrNull(event.target.value),
                )
              }
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700 lg:col-span-2">
            Eşlik eden belirtiler
            <textarea
              rows={4}
              value={value.presenting_complaint.associated_symptoms ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateComplaint(
                  'associated_symptoms',
                  textOrNull(event.target.value),
                )
              }
              placeholder="Ateş, bulantı, kilo kaybı, nefes darlığı, ağrı, döküntü..."
              className={TEXTAREA_CLASS}
            />
          </label>
        </div>
      </FormSection>

      <FormSection
        title="Klinik Öykü"
        description="Mevcut hastalık öyküsü, özgeçmiş, aile öyküsü, ilaçlar ve risk faktörleri."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {[
            [
              'history_of_present_illness',
              'Mevcut hastalık öyküsü',
              'Şikayetlerin başlangıcı, seyri, tetikleyen veya azaltan faktörler...',
            ],
            [
              'current_medical_conditions',
              'Bilinen mevcut hastalıklar',
              'Diyabet, hipertansiyon, tiroid hastalığı, kronik hastalıklar...',
            ],
            [
              'past_medical_history',
              'Özgeçmiş',
              'Önceki hastalıklar, yatışlar ve önemli klinik olaylar...',
            ],
            [
              'family_history',
              'Aile öyküsü',
              'Ailede kalıtsal, kardiyovasküler, onkolojik veya metabolik hastalıklar...',
            ],
            [
              'medications',
              'Kullanılan ilaçlar',
              'İlaç adı, doz, kullanım sıklığı ve süresi...',
            ],
            [
              'allergies',
              'Alerjiler',
              'İlaç, gıda, lateks veya diğer alerjiler ve reaksiyonlar...',
            ],
            [
              'tobacco_alcohol',
              'Sigara / alkol',
              'Miktar, sıklık, kullanım süresi veya bırakma tarihi...',
            ],
            [
              'past_surgeries',
              'Geçirilmiş ameliyatlar',
              'Ameliyat türü, tarih ve varsa komplikasyonlar...',
            ],
          ].map(([key, label, placeholder]) => (
            <label key={key} className="text-sm font-medium text-slate-700">
              {label}
              <textarea
                rows={4}
                value={
                  value.clinical_history_details[
                    key as keyof ClinicalIntakeInput['clinical_history_details']
                  ] ?? ''
                }
                onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
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
        title="Fizik Muayene"
        description="Vital bulgular ve serbest metin muayene bulguları."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <label className="text-sm font-medium text-slate-700">
            Kan basıncı sistolik
            <input
              type="number"
              min={40}
              max={300}
              value={value.physical_exam.blood_pressure_systolic ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam(
                  'blood_pressure_systolic',
                  numberOrNull(event.target.value),
                )
              }
              placeholder="mmHg"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Kan basıncı diyastolik
            <input
              type="number"
              min={20}
              max={200}
              value={value.physical_exam.blood_pressure_diastolic ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam(
                  'blood_pressure_diastolic',
                  numberOrNull(event.target.value),
                )
              }
              placeholder="mmHg"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Nabız
            <input
              type="number"
              min={20}
              max={300}
              value={value.physical_exam.pulse_bpm ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam('pulse_bpm', numberOrNull(event.target.value))
              }
              placeholder="/dk"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Ateş
            <input
              type="number"
              min={30}
              max={45}
              step="0.1"
              value={value.physical_exam.temperature_c ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam('temperature_c', numberOrNull(event.target.value))
              }
              placeholder="°C"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Solunum sayısı
            <input
              type="number"
              min={4}
              max={80}
              value={value.physical_exam.respiratory_rate ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam('respiratory_rate', numberOrNull(event.target.value))
              }
              placeholder="/dk"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700">
            Oksijen satürasyonu
            <input
              type="number"
              min={0}
              max={100}
              step="0.1"
              value={value.physical_exam.oxygen_saturation_percent ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam(
                  'oxygen_saturation_percent',
                  numberOrNull(event.target.value),
                )
              }
              placeholder="%"
              className={INPUT_CLASS}
            />
          </label>

          <label className="text-sm font-medium text-slate-700 sm:col-span-2 lg:col-span-3 xl:col-span-6">
            Muayene bulguları
            <textarea
              rows={5}
              value={value.physical_exam.examination_findings ?? ''}
              onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                updateExam(
                  'examination_findings',
                  textOrNull(event.target.value),
                )
              }
              placeholder="Genel durum, sistem muayeneleri, pozitif ve negatif bulgular..."
              className={TEXTAREA_CLASS}
            />
          </label>
        </div>
      </FormSection>

      <FormSection
        title="Laboratuvar Sonuçları"
        description="PDF veya görüntü seçimi, otomatik değer tanıma, referans karşılaştırması ve anormal değer işaretleme akışı."
      >
        <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
          <div className="rounded-lg border border-dashed border-cyan-300 bg-cyan-50/40 p-4">
            <label className="text-sm font-semibold text-slate-800">
              PDF veya görüntü yükleme
              <input
                type="file"
                multiple
                accept=".pdf,application/pdf,image/*"
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  onChange({
                    ...value,
                    attachments: replaceAttachmentGroup(
                      value.attachments,
                      event.target.files,
                      ['laboratory'],
                      'laboratory',
                    ),
                  })
                }
                className="mt-3 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-cyan-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-cyan-800"
              />
            </label>
            <AttachmentList
              items={labAttachments}
              emptyText="Henüz laboratuvar eki seçilmedi."
            />
            <p className="mt-3 text-xs leading-5 text-slate-500">
              Metin tabanlı laboratuvar PDF&apos;si üstteki analiz yükleme alanından
              gönderildiğinde değerler otomatik çıkarılır. Bu seçim alanı ek dosya
              adlarını ve türlerini klinik kayda ekler.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            {[
              ['Otomatik değer tanıma', 'Desteklenen test adları ve sayısal sonuçlar ayrıştırılır.'],
              ['Referans karşılaştırması', 'Değerler uygun referans aralığıyla karşılaştırılır.'],
              ['Anormal değer işaretleme', 'LOW, HIGH ve değerlendirme gereken sonuçlar ayrılır.'],
            ].map(([title, description]) => (
              <div
                key={title}
                className="rounded-lg border border-emerald-200 bg-emerald-50 p-4"
              >
                <p className="text-sm font-semibold text-emerald-900">{title}</p>
                <p className="mt-2 text-xs leading-5 text-emerald-800">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </FormSection>

      <FormSection
        title="Görüntüleme Sonuçları"
        description="Radyoloji ve patoloji rapor metinleri ile DICOM/rapor ekleri."
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {[
            ['xray', 'Röntgen'],
            ['ultrasound', 'USG'],
            ['ct', 'BT'],
            ['mri', 'MR'],
            ['pet_ct', 'PET-BT'],
            ['pathology', 'Patoloji raporları'],
          ].map(([key, label]) => (
            <label key={key} className="text-sm font-medium text-slate-700">
              {label}
              <textarea
                rows={4}
                value={
                  value.imaging_results[
                    key as keyof ClinicalIntakeInput['imaging_results']
                  ] ?? ''
                }
                onChange={(event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
                  updateImaging(
                    key as keyof ClinicalIntakeInput['imaging_results'],
                    textOrNull(event.target.value),
                  )
                }
                placeholder={`${label} rapor bulguları ve sonuç...`}
                className={TEXTAREA_CLASS}
              />
            </label>
          ))}
        </div>

        <div className="mt-5 rounded-lg border border-dashed border-violet-300 bg-violet-50/40 p-4">
          <label className="text-sm font-semibold text-slate-800">
            DICOM veya rapor yükleme
            <input
              type="file"
              multiple
              accept=".dcm,.dicom,application/dicom,application/pdf,image/*"
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                onChange({
                  ...value,
                  attachments: replaceAttachmentGroup(
                    value.attachments,
                    event.target.files,
                    [
                      'xray',
                      'ultrasound',
                      'ct',
                      'mri',
                      'pet_ct',
                      'pathology',
                      'dicom',
                      'other',
                    ],
                    'dicom',
                  ),
                })
              }
              className="mt-3 block w-full text-sm text-slate-600 file:mr-4 file:rounded-lg file:border-0 file:bg-violet-700 file:px-4 file:py-2 file:text-sm file:font-semibold file:text-white hover:file:bg-violet-800"
            />
          </label>
          <AttachmentList
            items={imagingAttachments}
            emptyText="Henüz DICOM veya görüntüleme raporu seçilmedi."
          />
          <p className="mt-3 text-xs leading-5 text-slate-500">
            Bu aşamada dosya adı, türü ve boyutu klinik bağlama kaydedilir. Rapor
            içeriği için yukarıdaki ilgili metin alanını kullanın.
          </p>
        </div>
      </FormSection>
    </div>
  );
}
