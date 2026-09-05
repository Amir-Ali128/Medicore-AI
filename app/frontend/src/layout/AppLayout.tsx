import { Outlet } from 'react-router-dom';

import DoctorFriendlyTurkish from '../components/DoctorFriendlyTurkish';
import FrontendTurkishLocalizer from '../components/FrontendTurkishLocalizer';
import NewRecordTerminology from '../components/NewRecordTerminology';
import PatientPersistenceBridge from '../components/PatientPersistenceBridge';
import RadiologyTerminologyLocalizer from '../components/RadiologyTerminologyLocalizer';
import WorkflowViewSimplifier from '../components/WorkflowViewSimplifier';
import { getAuthenticatedRole } from '../services/authClient';
import AdminMobileNavigation from './AdminMobileNavigation';
import AdminSidebar from './AdminSidebar';
import MobileNavigation from './MobileNavigation';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout() {
  const isAdmin = getAuthenticatedRole() === 'admin';

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <FrontendTurkishLocalizer />
      {!isAdmin ? (
        <>
          <DoctorFriendlyTurkish />
          <RadiologyTerminologyLocalizer />
          <NewRecordTerminology />
          <PatientPersistenceBridge />
          <WorkflowViewSimplifier />
        </>
      ) : null}

      {isAdmin ? <AdminSidebar /> : <Sidebar />}

      <div className="min-h-screen lg:pl-72">
        <Topbar />
        <main className="px-3 py-4 pb-28 sm:px-6 sm:py-6 lg:px-10 lg:py-8 lg:pb-8">
          <Outlet />
        </main>
      </div>

      {isAdmin ? <AdminMobileNavigation /> : <MobileNavigation />}
    </div>
  );
}
