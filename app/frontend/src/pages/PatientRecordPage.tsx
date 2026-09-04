import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import ManualLabEntrySection from '../components/lab/ManualLabEntrySection';
import SectionCard from '../components/ui/SectionCard';
import { createAnonymizedClinicalFixture } from '../fixtures/anonymizedClinicalFixture';
import { getStoredUser } from '../services/authClient';
import type { ClinicalIntakeInput } from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  activatePatientRecord,
  clearActivePatientRecord,
  getActivePatientId,
  getActivePatientProtocolNo,
  listPatientRecords,
  savePatientRecord,
} from '../services/patientClient';
import {
  createManualRadiologyReport,
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';
import {
  maskPatientName,
  privacyModeLabel,
  shouldMaskPatientIdentifiers,
} from '../services/privacyMode';

export { ACTIVE_CLINICAL_INTAKE_KEY };

function isDemoMode() {
  return import.meta.env.VITE_DEMO_MODE === 'true';
}

function privacySafeStoredIntake(
  clinicalIntake: ClinicalIntakeInput,
): ClinicalIntakeInput {
  if (!shouldMaskPatientIdentifiers()) return clinicalIntake;

  return {
    ...clinicalIntake,
    patient_information: {
      ...clinicalIntake.patient_information,
      full_name: clinicalIntake.patient_information.full_name
        ? maskPatientName(clinicalIntake.patient_information.full_name)
        : null,
    },
  };
}

function readStoredClinicalIntake(): ClinicalIntakeInput {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    if (raw) return JSON.parse(raw) as ClinicalIntakeInput;
    if (isDemoMode()) return createAnonymizedClinicalFixture();
    return createEmptyClinicalIntake();
  } catch {
    return isDemoMode()
      ? createAnonymizedClinicalFixture()
      : createEmptyClinicalIntake();
  }
}

function formatDate(value: string | null | undefined) {
  if (!value) return 'Tarih yok';
  try {
    return new Intl.DateTimeFormat('tr-TR', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export default function PatientRecordPage() {
  const user = getStoredUser();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const isNewPatientMode = searchParams.get('new') === '1';
  const hadStoredIntakeAtMount = useRef(
    Boolean(localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY)),
  );

  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput>(() =>
    isNewPatientMode ? createEmptyClinicalIntake() : readStoredClinicalIntake(),
  );
  const [protocolNo, setProtocolNo] = useState(() =>
    isNewPatientMode ? '' : getActivePatientProtocolNo() ?? '',
  );
  const [newModeReady, setNewModeReady] = useState(!isNewPatientMode);
  const [savedMessage, setSavedMessage] = useState('');
  const [restoreMessage, setRestoreMessage] = useState('');
  const [saveError, setSaveError] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [radiologyText, setRadiologyText] = useState('');
  const [radiologyReports, setRadiologyReports] = useState<RadiologyReport[]>([]);
  const [radiologyBusy, setRadiologyBusy] = useState(false);
  const [radiologyMessage, setRadiologyMessage] = useState('');
  const [radiologyError, setRadiologyError] = useState('');
  const privacyLabel = privacyModeLabel();
  const activePatientId = getActivePatientId();

  useEffect(() => {
    if (!isNewPatientMode) return;

    setNewModeReady(false);
    clearActivePatientRecord();
    setClinicalIntake(createEmptyClinicalIntake());
    setProtocolNo('');
    setSavedMessage('');
    setRestoreMessage('');
    setSaveError('');
    setRadiologyText('');
    setRadiologyReports([]);
    setNewModeReady(true);
  }, [isNewPatientMode]);

  useEffect(() => {
    let cancelled = false;

    async function restoreLatestAccountRecord() {
      // Explicit new-patient mode must never hydrate an older account record.
      if (
        isNewPatientMode ||
        isDemoMode() ||
        user?.role !== 'patient' ||
        hadStoredIntakeAtMount.current
      ) {
        return;
      }

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
        setProtocolNo(latest.protocol_no);
        setRestoreMessage('Daha önce kaydettiğiniz son hasta kaydı hesabınızdan yüklendi.');
        window.setTimeout(() => setRestoreMessage(''), 4000);
      } catch {
        // The empty/local form remains usable if account restoration is unavailable.
      }
    }

    void restoreLatestAccountRecord();
    return () => {
      cancelled = true;
    };
  }, [isNewPatientMode, user?.id, user?.role]);

  useEffect(() => {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(privacySafeStoredIntake(clinicalIntake)),
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
    let cancelled = false;
    const patientId = getActivePatientId();
    if (!patientId) {
      setRadiologyReports([]);
      return;
    }

    listPatientRadiologyReports(patientId, { includeUnanalyzed: true })
      .then((reports) => {
        if (!cancelled) setRadiologyReports(reports);
      })
      .catch(() => {
        if (!cancelled) setRadiologyReports([]);
      });

    return () => {
      cancelled = true;
    };
  }, [activePatientId, savedMessage]);

  function handleStartNewPatient() {
    clearActivePatientRecord();
    setClinicalIntake(createEmptyClinicalIntake());
    setProtocolNo('');
    setSavedMessage('');
    setSaveError('');
    setRadiologyText('');
    setRadiologyReports([]);
    navigate('/patients/demo?new=1', { replace: true });
  }

  async function handleSave() {
    localStorage.setItem(
      ACTIVE_CLINICAL_INTAKE_KEY,
      JSON.stringify(privacySafeStoredIntake(clinicalIntake)),
    );
    setSaveError('');
    setIsSaving(true);

    try {
      const record = await savePatientRecord(
        clinicalIntake,
        protocolNo.trim() || undefined,
      );
      setProtocolNo(record.protocol_no);
      setSavedMessage(
        isNewPatientMode
          ? `Yeni hasta kaydı oluşturuldu: ${record.protocol_no}`
          : `Hasta kaydı güncellendi: ${record.protocol_no}`,
      );
      navigate('/patients/demo', { replace: true });
      window.setTimeout(() => setSavedMessage(''), 4000);
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

  async function handleSaveRadiology() {
    const patientId = getActivePatientId();
    if (!patientId) {
      setRadiologyError('Önce hasta bilgilerini Kaydet ile arşive kaydetmelisin.');
      return;
    }
    if (radiologyText.trim().length < 10) {
      setRadiologyError('Rapor metni en az 10 karakter olmalıdır.');
      return;
    }

    setRadiologyBusy(true);
    setRadiologyError('');
    setRadiologyMessage('');
    try {
      const report = await createManualRadiologyReport({
        reportDate: new Date().toISOString().slice(0, 10),
        modality: null,
        bodyPart: null,
        reportText: radiologyText.trim(),
      });
      setRadiologyText('');
      setRadiologyReports((current) => [report, ...current]);
      setRadiologyMessage('Radyoloji / tetkik raporu hasta arşivine kaydedildi.');
      window.setTimeout(() => setRadiologyMessage(''), 4000);
    } catch (error) {
      setRadiologyError(
        error instanceof Error ? error.message : 'Radyoloji raporu kaydedilemedi.',
      );
    } finally {
      setRadiologyBusy(false);
    }
  }

  if (isNewPatientMode && !newModeReady) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-8 text-sm text-slate-500">
        Yeni hasta kaydı hazırlanıyor…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
            Hasta Yönetimi
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-950">
            {getActivePatientId() ? 'Hasta kaydı' : 'Yeni hasta kaydı'}
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            Hasta bilgileri, klinik öykü, manuel laboratuvar sonuçları ve radyoloji/tetkik raporlarını aynı hasta kaydı altında yönetin.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleStartNewPatient}
            className="rounded-lg bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800"
          >
            + Yeni Hasta
          </button>
          <button
            type="button"
            onClick={() => navigate('/patient-history')}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Hasta Arşivi
          </button>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Durum</p>
          <p className="mt-2 text-lg font-semibold text-slate-950">
            {getActivePatientId() ? 'Kayıtlı hasta' : 'Henüz kaydedilmedi'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Protokol / Hasta No</p>
          <p className="mt-2 break-all text-lg font-semibold text-slate-950">
            {(getActivePatientProtocolNo() ?? protocolNo) || 'Otomatik oluşturulacak'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ek kayıtlar</p>
          <p className="mt-2 text-lg font-semibold text-slate-950">
            {radiologyReports.length} radyoloji / tetkik
          </p>
        </div>
      </div>

      <SectionCard
        title="Hasta bilgileri ve klinik öykü"
        description="Bu bölümdeki bilgiler hasta kaydının ana klinik içeriğidir. Kaydet düğmesi yeni hasta oluşturur veya açık olan hastayı günceller."
      >
        <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50/60 p-4">
          <label className="block max-w-md text-sm font-semibold text-slate-800">
            Protokol / Hasta No (isteğe bağlı)
            <input
              value={protocolNo}
              onChange={(event) => setProtocolNo(event.target.value.toUpperCase())}
              placeholder="Boş bırakırsan otomatik oluşturulur"
              maxLength={32}
              className="mt-2 block w-full rounded-lg border border-blue-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-950 placeholder:text-slate-400"
            />
          </label>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Arşivde çok sayıda hastayı ayırmak için kurum içi hasta/protokol numaranı girebilirsin.
          </p>
        </div>

        {privacyLabel ? (
          <div className="mb-4 rounded-lg border border-violet-200 bg-violet-50 px-4 py-3 text-sm font-medium text-violet-800">
            {privacyLabel}. Diğer geliştirme/demo ekranlarına yazılan doğrudan hasta tanımlayıcıları maskelenir.
          </div>
        ) : null}

        {restoreMessage ? (
          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm font-medium text-blue-800">
            {restoreMessage}
          </div>
        ) : null}

        <ClinicalIntakeForm
          key={isNewPatientMode ? 'new-patient-intake' : 'active-patient-intake'}
          value={clinicalIntake}
          onChange={setClinicalIntake}
        />

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={handleStartNewPatient}
            className="rounded-lg border border-slate-300 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Formu yeni hasta için temizle
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="rounded-lg bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? 'Kaydediliyor...' : getActivePatientId() ? 'Hasta kaydını güncelle' : 'Yeni hastayı kaydet'}
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

      <div>
        <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-950">Laboratuvar</h2>
            <p className="mt-1 text-sm text-slate-500">
              Her parametreyi manuel ekleyip ayrı ayrı kaydedebilir veya toplu analiz edip hasta arşivine ekleyebilirsin.
            </p>
          </div>
          {!getActivePatientId() ? (
            <span className="text-xs font-semibold text-amber-700">
              Önce yukarıdaki hasta kaydını oluştur.
            </span>
          ) : null}
        </div>
        <ManualLabEntrySection
          onAnalyzed={() => undefined}
          onSaved={() => {
            setSavedMessage('Laboratuvar kaydı hasta arşivine eklendi.');
            window.setTimeout(() => setSavedMessage(''), 3000);
          }}
        />
      </div>

      <SectionCard
        title="Radyoloji / Ultrason / Diğer Tetkikler"
        description="Rapor metnini manuel girip doğrudan aktif hasta kaydına ekleyin. Görsel veya dosya yüklemek için ayrıntılı radyoloji ekranını kullanabilirsiniz."
      >
        <textarea
          rows={6}
          value={radiologyText}
          onChange={(event) => setRadiologyText(event.target.value)}
          placeholder="Rapor metnini manuel olarak buraya girin..."
          className="block w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-3 text-sm leading-6 text-slate-950 placeholder:text-slate-400"
        />

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleSaveRadiology()}
            disabled={radiologyBusy}
            className="rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
          >
            {radiologyBusy ? 'Kaydediliyor…' : 'Raporu Kaydet'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/radiology')}
            className="rounded-lg border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Dosya / Görüntü Yükle
          </button>
        </div>

        {radiologyMessage ? (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {radiologyMessage}
          </div>
        ) : null}
        {radiologyError ? (
          <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {radiologyError}
          </div>
        ) : null}

        <div className="mt-6 border-t border-slate-200 pt-5">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-slate-950">Son tetkik kayıtları</h3>
            <span className="text-xs font-semibold text-slate-500">
              {radiologyReports.length} kayıt
            </span>
          </div>

          {radiologyReports.length === 0 ? (
            <p className="mt-3 rounded-lg bg-slate-50 p-4 text-sm text-slate-500">
              Bu hasta için henüz radyoloji / tetkik kaydı yok.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {radiologyReports.slice(0, 5).map((report) => (
                <div
                  key={report.id}
                  className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {report.file_name || report.modality || 'Manuel tetkik raporu'}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {formatDate(report.created_at)} · {report.body_part || 'Bölge belirtilmedi'}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-700">
                    Kaydedildi
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
