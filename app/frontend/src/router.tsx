import { Navigate, createHashRouter } from 'react-router-dom';

import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layout/AppLayout';
import AdminAiCostsPage from './pages/AdminAiCostsPage';
import AdminAnalyticsPage from './pages/AdminAnalyticsPage';
import AdminFeedbackPage from './pages/AdminFeedbackPage';
import AdminLoginPage from './pages/AdminLoginPage';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import PatientHistoryPage from './pages/PatientHistoryPage';
import SimpleCaseWorkspacePage from './pages/SimpleCaseWorkspacePage';
import UserFeedbackPage from './pages/UserFeedbackPage';

export const router = createHashRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/admin', element: <AdminLoginPage /> },
  { path: '/admin/login', element: <AdminLoginPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <HomePage /> },
          { path: '/case', element: <SimpleCaseWorkspacePage /> },
          { path: '/history', element: <PatientHistoryPage /> },
          { path: '/feedback', element: <UserFeedbackPage /> },

          { path: '/admin/analytics', element: <AdminAnalyticsPage /> },
          { path: '/admin/ai-costs', element: <AdminAiCostsPage /> },
          { path: '/admin/feedback', element: <AdminFeedbackPage /> },

          { path: '/patients/demo', element: <Navigate to="/case" replace /> },
          { path: '/patient-detail', element: <Navigate to="/case" replace /> },
          { path: '/lab-ingestion', element: <Navigate to="/case" replace /> },
          { path: '/case-import', element: <Navigate to="/case" replace /> },
          { path: '/radiology', element: <Navigate to="/case" replace /> },
          { path: '/combined-evaluation', element: <Navigate to="/case" replace /> },
          { path: '/case-evaluation', element: <Navigate to="/case" replace /> },
          { path: '/analysis/results', element: <Navigate to="/case" replace /> },
          { path: '/clinical-hypotheses', element: <Navigate to="/case" replace /> },
          { path: '/doctor-review', element: <Navigate to="/case" replace /> },
          { path: '/doctor-worklist', element: <Navigate to="/case" replace /> },
          { path: '/patient-history', element: <Navigate to="/history" replace /> },
          { path: '/send', element: <Navigate to="/case" replace /> },
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);
