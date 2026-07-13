import { Outlet } from 'react-router-dom';
import DoctorFriendlyTurkish from '../components/DoctorFriendlyTurkish';
import FrontendTurkishLocalizer from '../components/FrontendTurkishLocalizer';
import PatientPersistenceBridge from '../components/PatientPersistenceBridge';
import WorkflowViewSimplifier from '../components/WorkflowViewSimplifier';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <FrontendTurkishLocalizer />
      <DoctorFriendlyTurkish />
      <PatientPersistenceBridge />
      <WorkflowViewSimplifier />
      <Sidebar />
      <div className="min-h-screen lg:pl-72">
        <Topbar />
        <main className="px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
