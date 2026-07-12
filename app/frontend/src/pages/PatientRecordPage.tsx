import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import ClinicalIntakeForm, {
  createEmptyClinicalIntake,
} from '../components/clinical/ClinicalIntakeForm';
import SectionCard from '../components/ui/SectionCard';
import {
  getAnalysisRunResults,
  type ClinicalIntakeInput,
  type LabAnalysisResult,
} from '../services/labAnalysisClient';
import {
  listPatientRadiologyReports,
  type RadiologyReport,
} from '../services/radiologyClient';

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

function formatDate(value: string | null) {
  if (!value) return 'Tarih belirtilmedi';
  return new Intl.DateTimeFormat('tr-TR', { dateStyle: 'medium' }).format(
    new Date(`${value}T12:00:00`),
  );
}

function modalityLabel(value: string) {
  const labels: Record<string, string> = {
    CT: 'BT',
    MRI: 'MR',
    XRAY: 'Röntgen',
    ULTRASOUND: 'Ultrasonografi',
    PET_CT: 'PET-BT',
    DEXA: 'DEXA',
  };
  return labels[value] ?? value;
}

function bodyPartLabel(value: string) {
  const labels: Record<string, string> = {
    BRAIN: 'Beyin',
    CHEST: 'Toraks',
    ABDOMEN: 'Abdomen',
    PELVIS: 'Pelvis',
    SPINE: 'Omurga',
    NECK: 'Boyun',
    BREAST: 'Meme',
    CARDIAC: 'Kalp',
    MUSCULOSKELETAL: 'Kas-iskelet',
    WHOLE_BODY: 'Tüm vücut',
    OTHER: 'Diğer',
  };
  return labels[value] ?? value;
}

function hasClinicalContent(value: ClinicalIntakeInput) {
  return Boolean(
    value.patient_information.full_name ||
      value.presenting_complaint.chief_complaint ||
      value.presenting_complaint.associated_symptoms ||
      value.clinical_history_details.history_of_present_illness ||
      value.clinical_history_details.past_medical_history ||
      value.physical_exam.examination_findings,
  );
}

export default function PatientRecordPage() {
  const [clinicalIntake, setClinicalIntake] = useState<ClinicalIntakeInput>(
    readStoredClinicalIntake,
  );
  const [savedMessage, setSavedMessage] = useState('');
  const [radiologyReports, setRadiologyReports] = useState<RadiologyReport[]>([]);
  const [labResults, setLabResults] = useState<LabAnalysisResult[]>([]);
  const [summaryError, setSummaryError] = useState('');
  const [isSummaryLoading, setIsSummaryLoading] = useState(true);

  const analysisRunId = localStorage.getItem('medicore:lastAnalysisRunId');

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

  useEffect(() => {
    async function loadSummary() {
      try {
        setIsSummaryLoading(true);
        setSummaryError('');

        const [reports, results] = await Promise.all([
          listPatientRadiologyReports().catch(() => []),
          analysisRunId
            ? getAnalysisRunResults(analysisRunId).catch(() => [])
            : Promise.resolve([]),
        ]);

        setRadiologyReports(reports);
        setLabResults(results);
      } catch (error) {
        setSummaryError(
          error instanceof Error
            ? error.message
            : 'Klinik özet yüklenemedi.',
        );
      } finally {
        setIsSummaryLoading(false);
      }
    }

    void loadSummary();
  }, [analysisRunId]);

  const abnormalLabResults = useMemo(
    () =>
      labResults.filter(
        (result) =>
          result.result_status === 'high' || result.result_status === 'low',
      ),
    [labResults],
  );

  const latestRadiology = radiologyReports[0] ?? null;
  const clinicalReady = hasClinicalContent(clinicalIntake);

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
            Klinik bilgiler, laboratuvar sonuçları ve görüntüleme raporları aynı hasta kaydında birlikte gösterilir.
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
        title="Klinik özet"
        description="Hastaya ait mevcut veri kaynaklarının hızlı görünümü."
      >
        {summaryError ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
            {summaryError}
          </div>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Klinik bilgiler
            </p>
            <p className="mt-3 text-2xl font-semibold text-slate-950">
              {clinicalReady ? 'Hazır' : 'Eksik'}
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {clinicalReady
                ? 'Şikâyet, öykü veya muayene bilgisi mevcut.'
                : 'Henüz klinik bilgi girilmedi.'}
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Laboratuvar
            </p>
            <p className="mt-3 text-2xl font-semibold text-slate-950">
              {labResults.length || 0} sonuç
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {abnormalLabResults.length} anormal sonuç işaretlendi.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Görüntüleme
            </p>
            <p className="mt-3 text-2xl font-semibold text-slate-950">
              {radiologyReports.length} rapor
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              {radiologyReports.reduce(
                (total, report) => total + report.critical_findings.length,
                0,
              )}{' '}
              kritik uyarı mevcut.
            </p>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Kullanılan kaynaklar
            </p>
            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <p>{clinicalReady ? '✓' : '○'} Klinik kayıt</p>
              <p>{labResults.length > 0 ? '✓' : '○'} Laboratuvar</p>
              <p>{radiologyReports.length > 0 ? '✓' : '○'} Radyoloji / DEXA</p>
            </div>
          </div>
        </div>

        {isSummaryLoading ? (
          <p className="mt-5 text-sm text-slate-500">Klinik özet yükleniyor…</p>
        ) : latestRadiology ? (
          <div className="mt-5 rounded-xl border border-cyan-200 bg-cyan-50/60 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-cyan-700">
                  Son görüntüleme raporu
                </p>
                <h3 className="mt-2 text-xl font-semibold text-slate-950">
                  {modalityLabel(latestRadiology.modality)} ·{' '}
                  {bodyPartLabel(latestRadiology.body_part)}
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  {formatDate(latestRadiology.report_date)}
                </p>
                <p className="mt-4 max-w-4xl text-sm leading-7 text-slate-700">
                  {latestRadiology.impression ?? latestRadiology.summary}
                </p>
              </div>
              <Link
                to="/radiology"
                className="shrink-0 rounded-lg bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-cyan-800"
              >
                Raporu aç
              </Link>
            </div>

            {latestRadiology.critical_findings.length > 0 ? (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4">
                <p className="text-sm font-semibold text-red-800">
                  Kritik uyarılar
                </p>
                <ul className="mt-2 space-y-1 text-sm text-red-800">
                  {latestRadiology.critical_findings.map((finding) => (
                    <li key={finding}>• {finding}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-600">
            Bu hasta için henüz görüntüleme raporu eklenmedi.
          </div>
        )}
      </SectionCard>

      {radiologyReports.length > 0 ? (
        <SectionCard
          title="Görüntüleme geçmişi"
          description="Bu hastaya eklenen son radyoloji ve DEXA raporları."
          action={
            <Link
              to="/radiology"
              className="rounded-lg border border-cyan-200 bg-white px-3 py-2 text-sm font-semibold text-cyan-800 hover:bg-cyan-50"
            >
              Tümünü aç
            </Link>
          }
        >
          <div className="space-y-3">
            {radiologyReports.slice(0, 5).map((report) => (
              <Link
                key={report.id}
                to="/radiology"
                className="block rounded-xl border border-slate-200 bg-white p-4 hover:border-cyan-300 hover:bg-cyan-50/30"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="font-semibold text-slate-950">
                      {modalityLabel(report.modality)} ·{' '}
                      {bodyPartLabel(report.body_part)}
                    </p>
                    <p className="mt-1 text-sm text-slate-500">
                      {formatDate(report.report_date)}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                      report.critical_findings.length > 0
                        ? 'bg-red-100 text-red-800'
                        : 'bg-emerald-100 text-emerald-800'
                    }`}
                  >
                    {report.critical_findings.length > 0
                      ? `${report.critical_findings.length} kritik uyarı`
                      : 'Kritik uyarı yok'}
                  </span>
                </div>
                <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-600">
                  {report.impression ?? report.summary}
                </p>
              </Link>
            ))}
          </div>
        </SectionCard>
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
        title="Yeni veri ekle"
        description="Bu hastaya laboratuvar veya radyoloji raporu ekleyebilirsiniz."
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
