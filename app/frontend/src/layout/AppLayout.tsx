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
    <div className="min-h-screen bg-[#f6f7f9] text-slate-950 lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <div className="hidden lg:block">
        {isAdmin ? <AdminSidebar /> : <Sidebar />}
      </div>

      <div className="min-w-0 min-h-screen">
        <Topbar />
        <main className="px-4 py-5 pb-28 sm:px-6 lg:px-8 lg:py-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      <div className="lg:hidden">
        {isAdmin ? <AdminMobileNavigation /> : <MobileNavigation />}
      </div>
    </div>
  );
}
