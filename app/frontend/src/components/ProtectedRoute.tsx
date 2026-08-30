import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { isAuthenticated } from '../services/authClient';

export default function ProtectedRoute() {
  const location = useLocation();

  if (!isAuthenticated()) {
    const loginPath = location.pathname.startsWith('/admin/')
      ? '/admin/login'
      : '/login';
    return <Navigate to={loginPath} replace state={{ from: location }} />;
  }

  return <Outlet />;
}
