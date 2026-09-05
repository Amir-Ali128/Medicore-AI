import { Navigate, Outlet, useLocation } from 'react-router-dom';

import {
  getAuthenticatedRole,
  isAuthenticated,
  type SessionWorkspace,
} from '../services/authClient';

const LEGAL_ACK_KEY = 'medicore:legalWarningsAcknowledged:v1';

function clinicalHome(role: string | null) {
  return role === 'patient' ? '/patients/demo' : '/analysis/mock';
}

function hasAcknowledgedClinicalWarnings() {
  try {
    return localStorage.getItem(LEGAL_ACK_KEY) === 'true';
  } catch {
    return false;
  }
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

  // The warning screen itself must remain reachable. Every other clinical route
  // is blocked until the user explicitly acknowledges the safety information.
  // This also covers direct/hash URL navigation, not just sidebar button clicks.
  if (
    workspace === 'clinical' &&
    location.pathname !== '/' &&
    !hasAcknowledgedClinicalWarnings()
  ) {
    return (
      <Navigate
        to="/"
        replace
        state={{ acknowledgementRequired: true, from: location }}
      />
    );
  }

  if (workspace === 'clinical' && role === null) {
    return <Navigate to={clinicalHome(role)} replace />;
  }

  return <Outlet />;
}
