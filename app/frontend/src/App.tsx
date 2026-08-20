import { RouterProvider } from 'react-router-dom';

import PresenceTracker from './components/PresenceTracker';
import { router } from './router';

export default function App() {
  return (
    <>
      <PresenceTracker />
      <RouterProvider router={router} />
    </>
  );
}
