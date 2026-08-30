import { Navigate, Outlet, useLocation } from 'react-router-dom';

import {
  getStoredUser,
  isAuthenticated,
  type AuthUser,
} from '../services/authClient';

function clinicalHome(user: AuthUser | null) {
  return user?.role === 'patient' ? '/patients/demo' : '/analysis/mock';
}

export default function ProtectedRoute() {
  const location = useLocation();

  if (!isAuthenticated()) {
    const loginPath = location.pathname.startsWith('/admin/')
      ? '/admin/login'
      : '/login';
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }

  const user = getStoredUser();
  const isAdminRoute = location.pathname.startsWith('/admin/');

  // Admin and clinical workspaces are deliberately separate. An authenticated
  // admin never falls through into patient/clinical screens, even by typing a
  // clinical URL manually.
  if (user?.role === 'admin' && !isAdminRoute) {
    return <Navigate to="/admin/analytics" replace />;
  }

  // Likewise, patient/doctor/lab accounts cannot enter the admin workspace by
  // manually editing the hash URL. Backend role checks remain the authority for
  // admin APIs; this guard keeps the UI/workspace boundary explicit as well.
  if (user?.role !== 'admin' && isAdminRoute) {
    return <Navigate to={clinicalHome(user)} replace />;
  }

  return <Outlet />;
}
