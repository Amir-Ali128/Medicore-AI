import { useEffect, useRef } from 'react';

import type { ClinicalIntakeInput } from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  ACTIVE_PATIENT_ID_KEY,
  savePatientRecord,
} from '../services/patientClient';

function readIntake(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function hasPatientName(intake: ClinicalIntakeInput | null): intake is ClinicalIntakeInput {
  return Boolean(intake?.patient_information.full_name?.trim());
}

export default function PatientPersistenceBridge() {
  const lastSaved = useRef('');
  const busy = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      const intake = readIntake();

      if (!hasPatientName(intake)) {
        lastSaved.current = '';
        return;
      }

      const serialized = JSON.stringify(intake);
      if (serialized === lastSaved.current || busy.current) return;

      busy.current = true;
      try {
        await savePatientRecord(intake);
        lastSaved.current = serialized;
      } catch {
        // The form remains available offline; the explicit save action can retry later.
      } finally {
        busy.current = false;
      }
    }, 1500);

    const clearHandler = () => {
      localStorage.removeItem(ACTIVE_PATIENT_ID_KEY);
      lastSaved.current = '';
    };
    window.addEventListener('medicore:new-patient', clearHandler);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener('medicore:new-patient', clearHandler);
    };
  }, []);

  return null;
}
