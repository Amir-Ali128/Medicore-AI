import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import type { ClinicalIntakeInput } from '../services/labAnalysisClient';

export const ACTIVE_CLINICAL_INTAKE_KEY = 'medicore:activeClinicalIntake';

function readStoredClinicalIntake(): ClinicalIntakeInput {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (!raw) return createEmptyClinicalIntake();
    return JSON.parse(raw) as ClinicalIntakeInput;
  } catch {
    return createEmptyClinicalIntake();
  }
}

function patientName(value: ClinicalIntakeInput) {
  return value.patient_information.full_name?.trim() || 'Yeni hasta';
}

export default function PatientRecordPage() {
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput>(
    readStoredClinicalIntake,
  );
  const [savedMessage, setSavedMessage] = useState('');

  useEffect(() => {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(clinicalIntake),
    );

    const patient = clinicalIntake.patient_information;
    if (patient.full_name) {
      localStorage.setItem('medicore:lastPatientDisplayName', patient.full_name);
    } else {
      localStorage.removeItem('medicore:lastPatientDisplayName');
    }

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

  function handleSave() {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(clinicalIntake),
    );
    setSavedMessage('Hasta bilgileri kaydedildi.');
    window.setTimeout(() => setSavedMessage(''), 2500);
  }

  function handleClearForm() {
    const confirmed = window.confirm(
      'Bu ekrandaki hasta bilgileri temizlensin mi? Bu işlem hasta geçmişine kayıt oluşturmaz.',
    );
    if (!confirmed) return;
    setClinicalIntake(createEmptyClinicalIntake());
    setSavedMessage('Form temizlendi.');
    window.setTimeout(() => setSavedMessage(''), 2500);
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
            Hasta kaydı
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            {patientName(clinicalIntake)}
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-500">
            Hastanın temel bilgilerini, şikâyetlerini, tıbbi öyküsünü ve muayene bulgularını bu ekranda kaydedin.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
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
            className="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Hasta bilgilerini kaydet
          </button>
        </div>
      </header>

      {savedMessage ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
          {savedMessage}
        </div>
      ) : null}

      <SectionCard
        title="Klinik kayıt"
        description="Alanlar isteğe bağlıdır. Kaydedilen bilgiler bu hastanın laboratuvar ve klinik değerlendirme sürecinde kullanılabilir."
      >
        <ClinicalIntakeForm
          value={clinicalIntake}
          onChange={setClinicalIntake}
        />
      </SectionCard>

      <SectionCard
        title="Sonraki adım"
        description="Hasta bilgilerini kaydettikten sonra laboratuvar veya radyoloji raporu ekleyebilirsiniz."
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
