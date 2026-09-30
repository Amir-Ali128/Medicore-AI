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
    <div className="relative min-h-screen bg-[#f6f7f9] text-slate-950">
      <div className="pointer-events-auto">
        {isAdmin ? <AdminSidebar /> : <Sidebar />}
      </div>

      <div className="relative z-0 min-h-screen pointer-events-auto lg:pl-64">
        <Topbar />
        <main className="relative z-0 px-4 py-5 pb-28 pointer-events-auto sm:px-6 lg:px-8 lg:py-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      <div className="pointer-events-auto">
        {isAdmin ? <AdminMobileNavigation /> : <MobileNavigation />}
      </div>
    </div>
  );
}
