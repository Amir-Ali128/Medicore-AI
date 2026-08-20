import { useEffect, useState } from 'react';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import type { ClinicalIntakeInput } from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  savePatientRecord,
} from '../services/patientClient';

export { ACTIVE_CLINICAL_INTAKE_KEY };

function readStoredClinicalIntake(): ClinicalIntakeInput {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return createEmptyClinicalIntake();
    return JSON.parse(raw) as ClinicalIntakeInput;
  } catch {
    return createEmptyClinicalIntake();
  }
}

export default function PatientRecordPage() {
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput>(
    readStoredClinicalIntake,
  );
  const [savedMessage, setSavedMessage] = useState('');
  const [saveError, setSaveError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(clinicalIntake),
    );

    localStorage.removeItem('medicore:lastPatientDisplayName');

    const patient = clinicalIntake.patient_information;
    if (patient.age !== null) {
      localStorage.setItem('medicore:lastPatientAge', String(patient.age));
    } else {
      localStorage.removeItem('medicore:lastPatientAge');
    }

    if (patient.sex) {
      localStorage.setItem('medicore:lastPatientSex', patient.sex);
    } else {
      localStorage.removeItem('medicore:lastPatientSex');
    }
  }, [clinicalIntake]);

  async function handleSave() {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(clinicalIntake),
    );
    setSaveError('');
    setIsSaving(true);

    try {
      await savePatientRecord(clinicalIntake);
      setSavedMessage('Hasta bilgileri kaydedildi.');
      window.setTimeout(() => setSavedMessage(''), 3000);
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : 'Hasta kaydı sunucuya kaydedilemedi.',
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionCard
        title="Hasta bilgileri"
        description="Klinik değerlendirmede kullanılacak temel bilgileri girin."
      >
        <ClinicalIntakeForm
          value={clinicalIntake}
          onChange={setClinicalIntake}
        />

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="w-full rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            {isSaving ? 'Kaydediliyor...' : 'Kaydet'}
          </button>
        </div>

        {savedMessage ? (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
            {savedMessage}
          </div>
        ) : null}

        {saveError ? (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">
            {saveError}
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}
