import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import type { ClinicalIntakeInput } from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  getActivePatientProtocolNo,
  savePatientRecord,
  type PatientRecord,
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
  const [protocolNo, setProtocolNo] = useState(
    () => getActivePatientProtocolNo() ?? '',
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

  useEffect(() => {
    const handlePatientSaved = (event: Event) => {
      const record = (event as CustomEvent<PatientRecord>).detail;
      if (record?.protocol_no) {
        setProtocolNo(record.protocol_no);
      }
    };

    window.addEventListener('medicore:patient-saved', handlePatientSaved);
    return () => {
      window.removeEventListener('medicore:patient-saved', handlePatientSaved);
    };
  }, []);

  async function handleSave() {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(clinicalIntake),
    );
    setSaveError('');

    const normalizedProtocolNo = protocolNo.trim().toUpperCase();
    if (!normalizedProtocolNo) {
      setSaveError('Protokol numarasını hasta girmelidir.');
      return;
    }

    setIsSaving(true);

    try {
      const record = await savePatientRecord(
        clinicalIntake,
        normalizedProtocolNo,
      );
      setProtocolNo(record.protocol_no);
      setSavedMessage(`Hasta kaydedildi. Protokol No: ${record.protocol_no}`);
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
        title="Protokol numarası"
        description="Protokol numarasını hasta kendisi girer. MediCore bu numarayı otomatik üretmez; yalnızca benzersiz olup olmadığını kontrol eder."
      >
        <div className="space-y-3">
          <label className="block text-sm font-semibold text-slate-800" htmlFor="patient-protocol-no">
            Hasta protokol numarası
          </label>
          <input
            id="patient-protocol-no"
            type="text"
            value={protocolNo}
            onChange={(event) => setProtocolNo(event.target.value.toUpperCase())}
            maxLength={32}
            autoCapitalize="characters"
            autoComplete="off"
            spellCheck={false}
            placeholder="Örn. 2026/001245"
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 font-mono text-lg font-semibold tracking-wide text-slate-950 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          />
          <p className="text-sm leading-6 text-slate-500">
            Harf, rakam, nokta, tire, alt çizgi ve / kullanılabilir. Aynı protokol numarası iki farklı hastaya verilemez.
          </p>
        </div>
      </SectionCard>

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
