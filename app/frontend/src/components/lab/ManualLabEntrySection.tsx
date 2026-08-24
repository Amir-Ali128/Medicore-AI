import { useEffect, useMemo, useState } from 'react';

import {
  createEmptyClinicalIntake,
  readStoredClinicalIntake,
} from '../clinical/ClinicalIntakeForm';
import {
  fetchManualLabOptions,
  submitManualLabResults,
  type LabAnalysisResponse,
  type ManualLabOption,
} from '../../services/labAnalysisClient';
import { saveLabReportToPatient } from '../../services/labArchiveClient';
import { getActivePatientId } from '../../services/patientClient';

type ManualRow = {
  id: string;
  testName: string;
  value: string;
  unit: string;
  referenceMin: string;
  referenceMax: string;
};

type Props = {
  onAnalyzed: (result: LabAnalysisResponse) => void;
  onSaved: (result: LabAnalysisResponse) => void | Promise<void>;
};

function rowId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function emptyRow(): ManualRow {
  return {
    id: rowId(),
    testName: '',
    value: '',
    unit: '',
    referenceMin: '',
    referenceMax: '',
  };
}

function localDateValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function parseOptionalNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

export default function ManualLabEntrySection({ onAnalyzed, onSaved }: Props) {
  const [options, setOptions] = useState<ManualLabOption[]>([]);
  const [rows, setRows] = useState<ManualRow[]>([emptyRow()]);
  const [reportDate, setReportDate] = useState(localDateValue());
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<LabAnalysisResponse | null>(null);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoadingOptions(true);
    fetchManualLabOptions()
      .then((loaded) => {
        if (active) setOptions(loaded);
      })
      .catch((loadError) => {
        if (!active) return;
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Manuel laboratuvar test listesi yüklenemedi.',
        );
      })
      .finally(() => {
        if (active) setLoadingOptions(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const optionsByName = useMemo(
    () => new Map(options.map((option) => [option.name, option])),
    [options],
  );

  function invalidateAnalysis() {
    setAnalysisResult(null);
    setSaved(false);
    setMessage('');
  }

  function updateRow(id: string, patch: Partial<ManualRow>) {
    invalidateAnalysis();
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
  }

  function changeTestName(id: string, testName: string) {
    const option = optionsByName.get(testName);
    updateRow(id, {
      testName,
      unit: option?.default_unit ?? '',
    });
  }

  function addRow() {
    invalidateAnalysis();
    setRows((current) => [...current, emptyRow()]);
  }

  function removeRow(id: string) {
    invalidateAnalysis();
    setRows((current) => {
      const next = current.filter((row) => row.id !== id);
      return next.length > 0 ? next : [emptyRow()];
    });
  }

  async function handleAnalyze() {
    const patientId = getActivePatientId();
    if (!patientId) {
      setError('Önce Hasta Bilgileri bölümünde Kaydet’e basarak aktif hasta oluşturmalısın.');
      return;
    }

    const completedRows = rows.filter(
      (row) => row.testName.trim() || row.value.trim() || row.unit.trim(),
    );
    if (completedRows.length === 0) {
      setError('En az bir laboratuvar sonucu girmelisin.');
      return;
    }

    const duplicateNames = completedRows
      .map((row) => row.testName)
      .filter((name, index, all) => name && all.indexOf(name) !== index);
    if (duplicateNames.length > 0) {
      setError(`Aynı test bir kez girilmeli: ${duplicateNames[0]}`);
      return;
    }

    const values = [] as {
      raw_parameter_name: string;
      normalized_value: number;
      unit: string;
      extracted_reference_min: number | null;
      extracted_reference_max: number | null;
      measured_at: string | null;
    }[];

    for (const row of completedRows) {
      if (!row.testName) {
        setError('Her satırda bir test adı seçmelisin.');
        return;
      }
      const normalizedValue = Number(row.value.replace(',', '.'));
      if (!Number.isFinite(normalizedValue)) {
        setError(`${row.testName} için geçerli bir sonuç değeri gir.`);
        return;
      }

      const referenceMin = parseOptionalNumber(row.referenceMin);
      const referenceMax = parseOptionalNumber(row.referenceMax);
      if (row.referenceMin.trim() && referenceMin === null) {
        setError(`${row.testName} için alt referans değeri geçersiz.`);
        return;
      }
      if (row.referenceMax.trim() && referenceMax === null) {
        setError(`${row.testName} için üst referans değeri geçersiz.`);
        return;
      }

      values.push({
        raw_parameter_name: row.testName,
        normalized_value: normalizedValue,
        unit: row.unit,
        extracted_reference_min: referenceMin,
        extracted_reference_max: referenceMax,
        measured_at: reportDate,
      });
    }

    setIsAnalyzing(true);
    setError('');
    setMessage('');
    try {
      const clinicalContext = readStoredClinicalIntake() ?? createEmptyClinicalIntake();
      const result = await submitManualLabResults({
        patient_id: patientId,
        report_date: reportDate,
        clinical_context: clinicalContext,
        values,
      });
      setAnalysisResult(result);
      setSaved(false);
      onAnalyzed(result);
      setMessage(`${result.counts.total} manuel laboratuvar sonucu analiz edildi. Kaydet’e basınca hasta arşivine eklenir.`);
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : 'Manuel laboratuvar analizi başarısız oldu.',
      );
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleSave() {
    const patientId = getActivePatientId();
    if (!patientId || !analysisResult) return;

    setIsSaving(true);
    setError('');
    setMessage('');
    try {
      const clinicalContext = readStoredClinicalIntake() ?? createEmptyClinicalIntake();
      await saveLabReportToPatient(
        analysisResult.lab_report_id,
        patientId,
        clinicalContext,
        analysisResult.patient,
      );
      setSaved(true);
      setMessage('Manuel laboratuvar sonuçları aktif hastanın arşivine kaydedildi.');
      await onSaved(analysisResult);
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : 'Manuel laboratuvar sonuçları kaydedilemedi.',
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-slate-950">Manuel laboratuvar girişi</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            Test adını listeden seç, sonucu ve birimi gir. Referans alt/üst sınırları isteğe bağlıdır; boş bırakırsan sistem kendi referans çözümleyicisini kullanır.
          </p>
        </div>
        <label className="text-xs font-semibold text-slate-600">
          Rapor tarihi
          <input
            type="date"
            value={reportDate}
            onChange={(event) => {
              invalidateAnalysis();
              setReportDate(event.target.value);
            }}
            className="mt-1 block rounded-lg border border-slate-300 px-3 py-2 text-sm font-normal text-slate-800"
          />
        </label>
      </div>

      {loadingOptions ? (
        <p className="mt-4 text-sm text-slate-500">Desteklenen testler yükleniyor…</p>
      ) : (
        <div className="mt-4 space-y-3">
          {rows.map((row, index) => {
            const selectedOption = optionsByName.get(row.testName);
            const unitOptions = selectedOption?.unit_options ?? [''];
            return (
              <div
                key={row.id}
                className="grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 lg:grid-cols-[minmax(180px,2fr)_minmax(100px,1fr)_minmax(130px,1fr)_minmax(100px,1fr)_minmax(100px,1fr)_auto]"
              >
                <label className="text-xs font-semibold text-slate-600">
                  Test adı
                  <select
                    value={row.testName}
                    onChange={(event) => changeTestName(row.id, event.target.value)}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900"
                  >
                    <option value="">Seç…</option>
                    {options.map((option) => (
                      <option key={option.name} value={option.name}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-xs font-semibold text-slate-600">
                  Sonuç
                  <input
                    inputMode="decimal"
                    value={row.value}
                    onChange={(event) => updateRow(row.id, { value: event.target.value })}
                    placeholder="örn. 4,2"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900"
                  />
                </label>

                <label className="text-xs font-semibold text-slate-600">
                  Birim
                  <select
                    value={row.unit}
                    onChange={(event) => updateRow(row.id, { unit: event.target.value })}
                    disabled={!row.testName}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900 disabled:bg-slate-100"
                  >
                    {unitOptions.map((unit) => (
                      <option key={unit || 'unitless'} value={unit}>
                        {unit || 'Birimsiz'}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="text-xs font-semibold text-slate-600">
                  Ref. alt
                  <input
                    inputMode="decimal"
                    value={row.referenceMin}
                    onChange={(event) => updateRow(row.id, { referenceMin: event.target.value })}
                    placeholder="opsiyonel"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900"
                  />
                </label>

                <label className="text-xs font-semibold text-slate-600">
                  Ref. üst
                  <input
                    inputMode="decimal"
                    value={row.referenceMax}
                    onChange={(event) => updateRow(row.id, { referenceMax: event.target.value })}
                    placeholder="opsiyonel"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-normal text-slate-900"
                  />
                </label>

                <button
                  type="button"
                  onClick={() => removeRow(row.id)}
                  className="self-end rounded-lg border border-red-200 bg-white px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-50"
                  aria-label={`${index + 1}. manuel laboratuvar satırını sil`}
                >
                  Sil
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={addRow}
          disabled={loadingOptions}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          + Sonuç ekle
        </button>
        <button
          type="button"
          onClick={() => void handleAnalyze()}
          disabled={loadingOptions || isAnalyzing}
          className="rounded-lg bg-blue-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-800 disabled:opacity-50"
        >
          {isAnalyzing ? 'Analiz ediliyor…' : 'Manuel sonuçları analiz et'}
        </button>
        {analysisResult ? (
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saved || isSaving}
            className="rounded-lg bg-emerald-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-default disabled:bg-emerald-100 disabled:text-emerald-800"
          >
            {isSaving ? 'Kaydediliyor…' : saved ? '✓ Kaydedildi' : 'Kaydet'}
          </button>
        ) : null}
      </div>

      {message ? (
        <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {message}
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </section>
  );
}
