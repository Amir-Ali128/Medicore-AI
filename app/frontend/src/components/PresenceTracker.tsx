import { useEffect } from 'react';

import { getAccessToken } from '../services/authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_MEDICORE_API_BASE_URL ??
  'http://127.0.0.1:8000';

const VISITOR_ID_KEY = 'medicore-analytics:visitorId';
const HEARTBEAT_INTERVAL_MS = 30_000;

function getVisitorId(): string {
  const stored = sessionStorage.getItem(VISITOR_ID_KEY);
  if (stored) return stored;

  const visitorId =
    typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

  sessionStorage.setItem(VISITOR_ID_KEY, visitorId);
  return visitorId;
}

function currentRoute(): string {
  const hashRoute = window.location.hash.replace(/^#/, '');
  return hashRoute || window.location.pathname || '/';
}

function browserPlatform(): string | undefined {
  const nav = navigator as Navigator & {
    userAgentData?: { platform?: string };
  };

  return nav.userAgentData?.platform || navigator.platform || undefined;
}

async function sendHeartbeat(visitorId: string): Promise<void> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  try {
    await fetch(`${API_BASE_URL.replace(/\/$/, '')}/analytics/heartbeat`, {
      method: 'POST',
      headers,
      keepalive: true,
      body: JSON.stringify({
        visitor_id: visitorId,
        path: currentRoute(),
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        language: navigator.language,
        platform: browserPlatform(),
      }),
    });
  } catch {
    // Presence telemetry must never interrupt the clinical UI.
  }
}

export default function PresenceTracker() {
  useEffect(() => {
    const visitorId = getVisitorId();
    const heartbeat = () => void sendHeartbeat(visitorId);

    heartbeat();

    const intervalId = window.setInterval(heartbeat, HEARTBEAT_INTERVAL_MS);
    window.addEventListener('hashchange', heartbeat);

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') heartbeat();
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('hashchange', heartbeat);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, []);

  return null;
}
