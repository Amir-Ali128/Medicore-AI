import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';
import { installLabUiPolish } from './labUiPolish';
import { installPrivacyStorageGuard } from './services/privacyStorageGuard';

installPrivacyStorageGuard();
installLabUiPolish();

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
