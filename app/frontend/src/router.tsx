import { createBrowserRouter } from 'react-router-dom';

import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layout/AppLayout';
import AnalysisResultsPage from './pages/AnalysisResultsPage';
import ClinicalHypothesesPage from './pages/ClinicalHypothesesPage';
import DashboardPage from './pages/DashboardPage';
import DoctorReviewPage from './pages/DoctorReviewPage';
import DoctorWorklistPage from './pages/DoctorWorklistPage';
import ExtractionReviewPage from './pages/ExtractionReviewPage';
import LoginPage from './pages/LoginPage';
import MockAnalysisPage from './pages/MockAnalysisPage';
import PatientDetailPage from './pages/PatientDetailPage';
import TimelinePage from './pages/TimelinePage';

export const router = createBrowserRouter([
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
            element: <DashboardPage />,
          },
          {
            path: '/patients/demo',
            element: <PatientDetailPage />,
          },
          {
            path: '/patient-detail',
            element: <PatientDetailPage />,
          },
          {
            path: '/analysis/mock',
            element: <MockAnalysisPage />,
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
        ],
      },
    ],
  },
]);