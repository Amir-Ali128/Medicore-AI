import { Navigate, Outlet, useLocation } from 'react-router-dom';

import {
  getAuthenticatedRole,
  isAuthenticated,
} from '../services/authClient';

function clinicalHome(role: string | null) {
  return role === 'patient' ? '/patients/demo' : '/analysis/mock';
}

export default function ProtectedRoute() {
  const location = useLocation();

  if (!isAuthenticated()) {
    const loginPath = location.pathname.startsWith('/admin/')
      ? '/admin/login'
      : '/login';
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }

  const role = getAuthenticatedRole();
  const isAdminRoute = location.pathname.startsWith('/admin/');

  if (role === 'admin' && !isAdminRoute) {
    return <Navigate to="/admin/analytics" replace />;
  }

  if (role !== 'admin' && isAdminRoute) {
    return <Navigate to={clinicalHome(role)} replace />;
  }

  return <Outlet />;
}
