import { createHashRouter } from 'react-router-dom';

import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layout/AppLayout';
import AnalysisResultsPage from './pages/AnalysisResultsPage';
import ClinicalHypothesesPage from './pages/ClinicalHypothesesPage';
import DoctorReviewPage from './pages/DoctorReviewPage';
import DoctorWorklistPage from './pages/DoctorWorklistPage';
import ExtractionReviewPage from './pages/ExtractionReviewPage';
import LoginPage from './pages/LoginPage';
import MockAnalysisPage from './pages/MockAnalysisPage';
import ModulePreviewPage from './pages/ModulePreviewPage';
import PatientHistoryPage from './pages/PatientHistoryPage';
import PatientRecordPage from './pages/PatientRecordPage';
import RadiologyPage from './pages/RadiologyPage';
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
          {
            path: '/',
            element: <PatientRecordPage />,
          },
          {
            path: '/patients/demo',
            element: <PatientRecordPage />,
          },
          {
            path: '/patient-detail',
            element: <PatientRecordPage />,
          },
          {
            path: '/analysis/mock',
            element: <MockAnalysisPage />,
          },
          {
            path: '/radiology',
            element: <RadiologyPage />,
          },
          {
            path: '/roadmap/imaging',
            element: <ModulePreviewPage module="imaging" />,
          },
          {
            path: '/roadmap/pathology',
            element: <ModulePreviewPage module="pathology" />,
          },
          {
            path: '/roadmap/cardiology',
            element: <ModulePreviewPage module="cardiology" />,
          },
          {
            path: '/extraction-review',
            element: <ExtractionReviewPage />,
          },
          {
            path: '/analysis/results',
            element: <AnalysisResultsPage />,
          },
          {
            path: '/clinical-hypotheses',
            element: <ClinicalHypothesesPage />,
          },
          {
            path: '/doctor-review',
            element: <DoctorReviewPage />,
          },
          {
            path: '/doctor-worklist',
            element: <DoctorWorklistPage />,
          },
          {
            path: '/timeline',
            element: <TimelinePage />,
          },
          {
            path: '/patient-history',
            element: <PatientHistoryPage />,
          },
        ],
      },
    ],
  },
]);
