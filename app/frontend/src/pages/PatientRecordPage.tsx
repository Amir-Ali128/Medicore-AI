import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

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

  function handleClearForm() {
    const confirmed = window.confirm('Bu ekrandaki hasta bilgileri temizlensin mi?');
    if (!confirmed) return;
    setClinicalIntake(createEmptyClinicalIntake());
    setSavedMessage('Form temizlendi.');
    setSaveError('');
    window.setTimeout(() => setSavedMessage(''), 2500);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap justify-end gap-2">
        <button
          type="button"
          onClick={handleClearForm}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Formu temizle
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={isSaving}
          className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSaving ? 'Kaydediliyor...' : 'Hasta bilgilerini kaydet'}
        </button>
      </div>

      {savedMessage ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          {savedMessage}
        </div>
      ) : null}

      {saveError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">
          {saveError}
        </div>
      ) : null}

      <SectionCard
        title="Hasta bilgileri"
        description="Klinik değerlendirmede kullanılacak temel bilgileri girin."
      >
        <ClinicalIntakeForm
          value={clinicalIntake}
          onChange={setClinicalIntake}
        />
      </SectionCard>

      <SectionCard
        title="Yeni veri ekle"
        description="Laboratuvar veya radyoloji raporu ekleyebilirsiniz."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Link
            to="/analysis/mock"
            className="rounded-lg border border-blue-200 bg-blue-50 p-4 font-semibold text-blue-800 hover:bg-blue-100"
          >
            Laboratuvar raporu ekle
          </Link>
          <Link
            to="/radiology"
            className="rounded-lg border border-cyan-200 bg-cyan-50 p-4 font-semibold text-cyan-800 hover:bg-cyan-100"
          >
            Radyoloji raporu ekle
          </Link>
        </div>
      </SectionCard>
    </div>
  );
}
