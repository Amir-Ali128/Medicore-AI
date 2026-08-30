import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';

import { getStoredUser } from '../services/authClient';
import {
  getClinicalHypothesesForAnalysisRun,
  type ClinicalHypothesis,
} from '../services/clinicalHypothesesClient';
import {
  LAST_ANALYSIS_RUN_ID_KEY,
  type ClinicalIntakeInput,
} from '../services/labAnalysisClient';
import {
  ACTIVE_CLINICAL_INTAKE_KEY,
  ACTIVE_PATIENT_PROTOCOL_KEY,
} from '../services/patientClient';

type NavItem = {
  label: string;
  to: string;
  adminOnly?: boolean;
  patientOnly?: boolean;
};

type CaseSummary = {
  patientName: string | null;
  age: number | null;
  sex: string | null;
  protocolNo: string | null;
  complaint: string | null;
  risk: number | null;
  pathologicalCount: number | null;
  pathologicalPreview: string[];
  requiresReview: boolean;
};

const items: NavItem[] = [
  { label: '🏠 Ana Sayfa', to: '/' },
  { label: '📡 Canlı Trafik', to: '/admin/analytics', adminOnly: true },
  { label: '💬 Geri Bildirimler', to: '/admin/feedback', adminOnly: true },
  { label: '👤 Hasta Bilgileri', to: '/patients/demo' },
  { label: '🩸 Laboratuvar Sonuçları', to: '/analysis/mock' },
  { label: '🩻 Radyoloji ve Diğer Tetkik Raporları', to: '/radiology' },
  { label: '🧩 Bulguları Değerlendir', to: '/combined-evaluation' },
  { label: '📄 Arşiv', to: '/patient-history' },
  { label: '✉️ Gönder', to: '/send' },
  { label: '💡 Önerileriniz', to: '/feedback', patientOnly: true },
];

const getLinkClassName = ({ isActive }: { isActive: boolean }) =>
  [
    'flex items-center rounded-lg px-3 py-2.5 text-sm font-medium leading-5 transition',
    isActive
      ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950',
  ].join(' ');

function readClinicalIntake(): ClinicalIntakeInput | null {
  try {
    const raw = localStorage.getItem(ACTIVE_CLINICAL_INTAKE_KEY);
    return raw ? (JSON.parse(raw) as ClinicalIntakeInput) : null;
  } catch {
    return null;
  }
}

function getNewestCompactHypothesis(hypotheses: ClinicalHypothesis[]) {
  return hypotheses.find(
    (item) =>
      item.hypothesis_type === 'compact_risk_summary' ||
      item.metadata_json?.compact_mode === true,
  );
}

function metadataNumber(metadata: Record<string, unknown> | undefined, key: string) {
  const value = metadata?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function buildPathologicalPreview(metadata: Record<string, unknown> | undefined) {
  const raw = metadata?.pathological_findings;
  if (!Array.isArray(raw)) return [];

  return raw
    .map((item) => {
      if (!item || typeof item !== 'object') return null;
      const finding = item as Record<string, unknown>;
      if (typeof finding.display === 'string' && finding.display.trim()) {
        return finding.display.trim();
      }

      const name = typeof finding.name === 'string' ? finding.name.trim() : '';
      const value =
        typeof finding.value === 'string' || typeof finding.value === 'number'
          ? String(finding.value)
          : '';
      const unit = typeof finding.unit === 'string' ? finding.unit.trim() : '';
      const status =
        typeof finding.status_label === 'string' ? finding.status_label.trim() : '';

      if (!name) return null;
      return [name, value, unit, status ? `(${status})` : '']
        .filter(Boolean)
        .join(' ');
    })
    .filter((value): value is string => Boolean(value))
    .slice(0, 3);
}

function buildComplaint(intake: ClinicalIntakeInput | null) {
  const complaint = intake?.presenting_complaint;
  const text =
    complaint?.chief_complaint ||
    complaint?.reason_for_visit ||
    complaint?.associated_symptoms ||
    null;

  if (!text) return null;
  const cleaned = text.replace(/\s+/g, ' ').trim();
  return cleaned.length > 82 ? `${cleaned.slice(0, 79)}…` : cleaned;
}

function riskLabel(risk: number | null) {
  if (risk === 1) return 'Düşük';
  if (risk === 2) return 'Orta';
  if (risk === 3) return 'Yüksek';
  return 'Bekliyor';
}

function riskClass(risk: number | null) {
  if (risk === 1) return 'bg-emerald-100 text-emerald-800';
  if (risk === 2) return 'bg-amber-100 text-amber-800';
  if (risk === 3) return 'bg-red-100 text-red-800';
  return 'bg-slate-100 text-slate-600';
}

export default function Sidebar() {
  const user = getStoredUser();
  const location = useLocation();
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);

  const visibleItems = items.filter((item) => {
    if (item.adminOnly && user?.role !== 'admin') return false;
    if (item.patientOnly && user?.role !== 'patient') return false;
    return true;
  });

  useEffect(() => {
    let cancelled = false;

    async function loadCaseSummary() {
      const intake = readClinicalIntake();
      const patient = intake?.patient_information;
      const analysisRunId = localStorage.getItem(LAST_ANALYSIS_RUN_ID_KEY);
      let compact: ClinicalHypothesis | undefined;

      if (analysisRunId) {
        try {
          const hypotheses = await getClinicalHypothesesForAnalysisRun(analysisRunId);
          compact = getNewestCompactHypothesis(hypotheses);
        } catch {
          // Sidebar summary is optional; navigation must remain usable if the API is unavailable.
        }
      }

      if (cancelled) return;

      const metadata = compact?.metadata_json;
      const pathologicalFindings = metadata?.pathological_findings;
      const pathologicalCount =
        metadataNumber(metadata, 'pathological_count') ??
        (Array.isArray(pathologicalFindings) ? pathologicalFindings.length : null);

      const hasAnyCaseData = Boolean(intake || analysisRunId || compact);
      if (!hasAnyCaseData) {
        setCaseSummary(null);
        return;
      }

      setCaseSummary({
        patientName: patient?.full_name?.trim() || null,
        age: patient?.age ?? null,
        sex: patient?.sex?.trim() || null,
        protocolNo: localStorage.getItem(ACTIVE_PATIENT_PROTOCOL_KEY),
        complaint: buildComplaint(intake),
        risk: metadataNumber(metadata, 'risk'),
        pathologicalCount,
        pathologicalPreview: buildPathologicalPreview(metadata),
        requiresReview:
          compact?.needs_doctor_review === true ||
          metadata?.requires_physician_review === true,
      });
    }

    const refresh = () => void loadCaseSummary();
    void loadCaseSummary();
    window.addEventListener('storage', refresh);
    window.addEventListener('medicore:case-summary-updated', refresh);
    window.addEventListener('focus', refresh);

    return () => {
      cancelled = true;
      window.removeEventListener('storage', refresh);
      window.removeEventListener('medicore:case-summary-updated', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, [location.pathname]);

  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-72 flex-col border-r border-slate-200 bg-white px-5 py-6 lg:flex">
      <div className="mb-5">
        <Link
          to="/"
          aria-label="MediCore AI ana sayfa"
          className="inline-flex rounded-lg outline-none transition hover:opacity-80 focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-blue-600 text-lg font-bold text-white shadow-sm">
            M
          </div>
        </Link>
        <p className="mt-4 text-xs font-semibold uppercase text-cyan-700">
          Klinik Karar Desteği
        </p>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          İşleme başlamak için ilgili bölümü seçin.
        </p>
      </div>

      <nav className="space-y-1 overflow-y-auto pr-1">
        {visibleItems.map((item) => (
          <NavLink key={item.to} to={item.to} className={getLinkClassName}>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {caseSummary ? (
        <Link
          to="/combined-evaluation"
          className="mt-auto block rounded-xl border border-slate-200 bg-slate-50 p-3.5 transition hover:border-blue-200 hover:bg-blue-50/50"
        >
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
              Aktif Vaka
            </p>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${riskClass(caseSummary.risk)}`}>
              Risk: {riskLabel(caseSummary.risk)}
            </span>
          </div>

          <p className="mt-2 truncate text-sm font-semibold text-slate-900">
            {caseSummary.patientName || 'Aktif hasta'}
          </p>

          <p className="mt-0.5 text-xs text-slate-500">
            {[
              caseSummary.age !== null ? `${caseSummary.age} yaş` : null,
              caseSummary.sex,
              caseSummary.protocolNo ? `Protokol ${caseSummary.protocolNo}` : null,
            ]
              .filter(Boolean)
              .join(' · ') || 'Temel hasta bilgisi bekleniyor'}
          </p>

          {caseSummary.complaint ? (
            <p className="mt-2 text-xs leading-5 text-slate-600">
              {caseSummary.complaint}
            </p>
          ) : null}

          {caseSummary.pathologicalPreview.length > 0 ? (
            <div className="mt-3 rounded-lg bg-white p-2.5 ring-1 ring-slate-200">
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                Öne çıkan bulgular
              </p>
              <ul className="mt-1.5 space-y-1">
                {caseSummary.pathologicalPreview.map((finding) => (
                  <li key={finding} className="truncate text-[11px] leading-4 text-slate-700">
                    • {finding}
                  </li>
                ))}
              </ul>
              {(caseSummary.pathologicalCount ?? 0) > caseSummary.pathologicalPreview.length ? (
                <p className="mt-1 text-[10px] font-medium text-slate-400">
                  +{(caseSummary.pathologicalCount ?? 0) - caseSummary.pathologicalPreview.length} bulgu daha
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className="rounded-lg bg-white px-2.5 py-2 ring-1 ring-slate-200">
              <p className="text-[10px] font-semibold uppercase text-slate-400">Patolojik</p>
              <p className="mt-0.5 text-sm font-bold text-slate-900">
                {caseSummary.pathologicalCount ?? '—'}
              </p>
            </div>
            <div className="rounded-lg bg-white px-2.5 py-2 ring-1 ring-slate-200">
              <p className="text-[10px] font-semibold uppercase text-slate-400">Durum</p>
              <p className="mt-0.5 text-xs font-bold text-slate-900">
                {caseSummary.requiresReview ? 'Hekim kontrolü' : 'Değerlendirme bekliyor'}
              </p>
            </div>
          </div>
        </Link>
      ) : null}
    </aside>
  );
}
