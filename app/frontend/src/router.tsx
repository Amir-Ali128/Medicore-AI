import { createHashRouter } from 'react-router-dom';

import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layout/AppLayout';
import AnalysisResultsPage from './pages/AnalysisResultsPage';
import CaseEvaluationPage from './pages/CaseEvaluationPage';
import ClinicalHypothesesPage from './pages/ClinicalHypothesesPage';
import ClinicalSpecialtyPreviewPage from './pages/ClinicalSpecialtyPreviewPage';
import CombinedCaseWorkspacePage from './pages/CombinedCaseWorkspacePage';
import DoctorReviewPage from './pages/DoctorReviewPage';
import DoctorWorklistPage from './pages/DoctorWorklistPage';
import ExtractionReviewPage from './pages/ExtractionReviewPage';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import ModulePreviewPage from './pages/ModulePreviewPage';
import PatientHistoryPage from './pages/PatientHistoryPage';
import PatientRecordPage from './pages/PatientRecordPage';
import RadiologyEvaluationPage from './pages/RadiologyEvaluationPage';
import TimelinePage from './pages/TimelinePage';

export const router = createHashRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/patients/demo', element: <PatientRecordPage /> },
          { path: '/patient-detail', element: <PatientRecordPage /> },
          { path: '/analysis/mock', element: <CombinedCaseWorkspacePage /> },
          { path: '/case-import', element: <CombinedCaseWorkspacePage /> },
          { path: '/radiology', element: <RadiologyEvaluationPage /> },
          { path: '/combined-evaluation', element: <CaseEvaluationPage /> },
          { path: '/roadmap/radiology', element: <ModulePreviewPage module="radiology" /> },
          { path: '/roadmap/imaging', element: <ModulePreviewPage module="imaging" /> },
          { path: '/roadmap/pathology', element: <ModulePreviewPage module="pathology" /> },
          { path: '/roadmap/cardiology', element: <ModulePreviewPage module="cardiology" /> },
          { path: '/roadmap/microbiology', element: <ModulePreviewPage module="microbiology" /> },

          { path: '/clinics/internal-medicine', element: <ClinicalSpecialtyPreviewPage specialty="internal-medicine" /> },
          { path: '/clinics/pulmonology', element: <ClinicalSpecialtyPreviewPage specialty="pulmonology" /> },
          { path: '/clinics/neurology', element: <ClinicalSpecialtyPreviewPage specialty="neurology" /> },
          { path: '/clinics/hematology', element: <ClinicalSpecialtyPreviewPage specialty="hematology" /> },
          { path: '/clinics/infectious-diseases', element: <ClinicalSpecialtyPreviewPage specialty="infectious-diseases" /> },
          { path: '/clinics/nephrology', element: <ClinicalSpecialtyPreviewPage specialty="nephrology" /> },
          { path: '/clinics/gastroenterology', element: <ClinicalSpecialtyPreviewPage specialty="gastroenterology" /> },
          { path: '/clinics/endocrinology', element: <ClinicalSpecialtyPreviewPage specialty="endocrinology" /> },
          { path: '/clinics/oncology', element: <ClinicalSpecialtyPreviewPage specialty="oncology" /> },
          { path: '/clinics/rheumatology', element: <ClinicalSpecialtyPreviewPage specialty="rheumatology" /> },
          { path: '/clinics/pediatrics', element: <ClinicalSpecialtyPreviewPage specialty="pediatrics" /> },
          { path: '/clinics/obstetrics-gynecology', element: <ClinicalSpecialtyPreviewPage specialty="obstetrics-gynecology" /> },
          { path: '/clinics/emergency-medicine', element: <ClinicalSpecialtyPreviewPage specialty="emergency-medicine" /> },

          { path: '/extraction-review', element: <ExtractionReviewPage /> },
          { path: '/analysis/results', element: <AnalysisResultsPage /> },
          { path: '/clinical-hypotheses', element: <ClinicalHypothesesPage /> },
          { path: '/doctor-review', element: <DoctorReviewPage /> },
          { path: '/doctor-worklist', element: <DoctorWorklistPage /> },
          { path: '/timeline', element: <TimelinePage /> },
          { path: '/patient-history', element: <PatientHistoryPage /> },
        ],
      },
    ],
  },
]);
