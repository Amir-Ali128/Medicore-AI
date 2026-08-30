import { Navigate, Outlet, useLocation } from 'react-router-dom';

import {
  getAuthenticatedRole,
  isAuthenticated,
  type SessionWorkspace,
} from '../services/authClient';

function clinicalHome(role: string | null) {
  return role === 'patient' ? '/patients/demo' : '/analysis/mock';
}

export default function ProtectedRoute() {
  const location = useLocation();
  const isAdminRoute = location.pathname.startsWith('/admin/');
  const workspace: SessionWorkspace = isAdminRoute ? 'admin' : 'clinical';

  if (!isAuthenticated(workspace)) {
    const loginPath = isAdminRoute ? '/admin/login' : '/login';
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }

  const role = getAuthenticatedRole(workspace);

  if (workspace === 'admin' && role !== 'admin') {
    return <Navigate to="/admin/login" replace />;
  }

  if (workspace === 'clinical' && role === 'admin') {
    return <Navigate to="/admin/analytics" replace />;
  }

  if (workspace === 'clinical' && role === null) {
    return <Navigate to={clinicalHome(role)} replace />;
  }

  return <Outlet />;
}
