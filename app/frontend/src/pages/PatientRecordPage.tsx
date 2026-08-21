import { useEffect, useRef, useState } from 'react';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import { getStoredUser } from '../services/authClient';
import type { ClinicalIntakeInput } from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  activatePatientRecord,
  listPatientRecords,
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
  const user = getStoredUser();
  const hadStoredIntakeAtMount = useRef(
    Boolean(localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY)),
  );
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput>(
    readStoredClinicalIntake,
  );
  const [savedMessage, setSavedMessage] = useState('');
  const [restoreMessage, setRestoreMessage] = useState('');
  const [saveError, setSaveError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function restoreLatestAccountRecord() {
      if (user?.role !== 'patient' || hadStoredIntakeAtMount.current) return;

      try {
        const records = await listPatientRecords();
        if (cancelled) return;

        const latest = records.find(
          (record) => Boolean(record.metadata_json?.clinical_context),
        );
        const storedIntake = latest?.metadata_json?.clinical_context;
        if (!latest || !storedIntake) return;

        activatePatientRecord(latest);
        setClinicalIntake(storedIntake);
        setRestoreMessage('Daha önce kaydettiğiniz bilgiler hesabınızdan yüklendi.');
        window.setTimeout(() => setRestoreMessage(''), 4000);
      } catch {
        // The empty/local form remains usable if account restoration is unavailable.
      }
    }

    void restoreLatestAccountRecord();
    return () => {
      cancelled = true;
    };
  }, [user?.id, user?.role]);

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
      setSavedMessage('Hasta bilgileri kaydedildi ve arşiv güncellendi.');
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
        description="Klinik değerlendirmede kullanılacak temel bilgileri girin. Kaydettiğiniz bilgiler sonraki girişlerinizde hesabınızdan yeniden yüklenir."
      >
        {restoreMessage ? (
          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800">
            {restoreMessage}
          </div>
        ) : null}

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
