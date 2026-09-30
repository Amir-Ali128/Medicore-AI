import { createHashRouter } from 'react-router-dom';

import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './layout/AppLayout';
import AdminAiCostsPage from './pages/AdminAiCostsPage';
import AdminAnalyticsPage from './pages/AdminAnalyticsPage';
import AdminFeedbackPage from './pages/AdminFeedbackPage';
import AdminLoginPage from './pages/AdminLoginPage';
import LoginPage from './pages/LoginPage';
import SimpleWorkspacePage from './pages/SimpleWorkspacePage';

export const router = createHashRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/admin',
    element: <AdminLoginPage />,
  },
  {
    path: '/admin/login',
    element: <AdminLoginPage />,
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: '/', element: <SimpleWorkspacePage /> },
          { path: '/workspace', element: <SimpleWorkspacePage /> },
          { path: '/admin/analytics', element: <AdminAnalyticsPage /> },
          { path: '/admin/ai-costs', element: <AdminAiCostsPage /> },
          { path: '/admin/feedback', element: <AdminFeedbackPage /> },
        ],
      },
    ],
  },
]);
