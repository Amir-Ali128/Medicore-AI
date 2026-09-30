import { Outlet } from 'react-router-dom';

import { getAuthenticatedRole } from '../services/authClient';
import AdminMobileNavigation from './AdminMobileNavigation';
import AdminSidebar from './AdminSidebar';
import MobileNavigation from './MobileNavigation';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout() {
  const isAdmin = getAuthenticatedRole() === 'admin';

  return (
    <div className="min-h-screen bg-[#f5f7fb] text-slate-950">
      {isAdmin ? <AdminSidebar /> : <Sidebar />}

      <div className="min-h-screen lg:pl-64">
        <Topbar />
        <main className="px-3 py-4 pb-24 sm:px-6 sm:py-6 lg:px-8 lg:py-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      {isAdmin ? <AdminMobileNavigation /> : <MobileNavigation />}
    </div>
  );
}
