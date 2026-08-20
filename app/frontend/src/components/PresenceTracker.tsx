import { useEffect } from 'react';

import { getAccessToken } from '../services/authClient';

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ??
  import.meta.env.VITE_MEDICORE_API_BASE_URL ??
  'http://127.0.0.1:8000';

const VISITOR_ID_KEY = 'medicore-analytics:visitorId';
const HEARTBEAT_INTERVAL_MS = 30_000;

type BrowserBrandVersion = {
  brand: string;
  version: string;
};

type UserAgentDataLike = {
  brands?: BrowserBrandVersion[];
  mobile?: boolean;
  platform?: string;
  getHighEntropyValues?: (hints: string[]) => Promise<{
    architecture?: string;
    bitness?: string;
    fullVersionList?: BrowserBrandVersion[];
    mobile?: boolean;
    model?: string;
    platform?: string;
    platformVersion?: string;
  }>;
};

type DeviceDetails = {
  device_brand?: string;
  device_model?: string;
  device_type?: 'mobile' | 'tablet' | 'desktop';
  os_name?: string;
  os_version?: string;
  browser_name?: string;
  browser_version?: string;
  architecture?: string;
};

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
  const nav = navigator as Navigator & { userAgentData?: UserAgentDataLike };
  return nav.userAgentData?.platform || navigator.platform || undefined;
}

function inferBrand(model?: string): string | undefined {
  if (!model) return undefined;
  if (/^SM-/i.test(model)) return 'Samsung';
  if (/^Pixel\b/i.test(model)) return 'Google';
  if (/^iPhone$/i.test(model) || /^iPad$/i.test(model)) return 'Apple';
  return undefined;
}

function fallbackDeviceDetails(): DeviceDetails {
  const ua = navigator.userAgent;
  const android = ua.match(/Android\s+([\d.]+)/i);
  const androidModel = ua.match(/Android[^;]*;\s*([^;)]+?)(?:\s+Build\/|;|\))/i)?.[1]?.trim();
  const ios = ua.match(/(?:iPhone|CPU(?: iPhone)? OS)\s*([\d_]+)/i);
  const mac = ua.match(/Mac OS X\s*([\d_]+)/i);
  const chrome = ua.match(/(?:Chrome|CriOS)\/([\d.]+)/i);
  const edge = ua.match(/Edg(?:A|iOS)?\/([\d.]+)/i);
  const firefox = ua.match(/(?:Firefox|FxiOS)\/([\d.]+)/i);
  const safari = !chrome && !edge ? ua.match(/Version\/([\d.]+).*Safari/i) : null;

  let browserName: string | undefined;
  let browserVersion: string | undefined;
  if (edge) {
    browserName = 'Edge';
    browserVersion = edge[1];
  } else if (chrome) {
    browserName = 'Chrome';
    browserVersion = chrome[1];
  } else if (firefox) {
    browserName = 'Firefox';
    browserVersion = firefox[1];
  } else if (safari) {
    browserName = 'Safari';
    browserVersion = safari[1];
  }

  const isIPhone = /iPhone/i.test(ua);
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isMobile = /Mobi|Android|iPhone/i.test(ua);
  const model = androidModel || (isIPhone ? 'iPhone' : isIPad ? 'iPad' : undefined);

  let osName: string | undefined;
  let osVersion: string | undefined;
  if (android) {
    osName = 'Android';
    osVersion = android[1];
  } else if (isIPhone || isIPad) {
    osName = 'iOS/iPadOS';
    osVersion = ios?.[1]?.replaceAll('_', '.');
  } else if (/Windows/i.test(ua)) {
    osName = 'Windows';
  } else if (/Mac OS X/i.test(ua)) {
    osName = 'macOS';
    osVersion = mac?.[1]?.replaceAll('_', '.');
  } else if (/Linux/i.test(ua)) {
    osName = 'Linux';
  }

  return {
    device_brand: inferBrand(model),
    device_model: model,
    device_type: isIPad ? 'tablet' : isMobile ? 'mobile' : 'desktop',
    os_name: osName,
    os_version: osVersion,
    browser_name: browserName,
    browser_version: browserVersion,
  };
}

function preferredBrowser(brands?: BrowserBrandVersion[]): BrowserBrandVersion | undefined {
  if (!brands?.length) return undefined;
  return brands.find((item) => !/not.?a.?brand|chromium/i.test(item.brand)) ?? brands[0];
}

async function readDeviceDetails(): Promise<DeviceDetails> {
  const fallback = fallbackDeviceDetails();
  const nav = navigator as Navigator & { userAgentData?: UserAgentDataLike };
  const uaData = nav.userAgentData;

  if (!uaData?.getHighEntropyValues) {
    return fallback;
  }

  try {
    const high = await uaData.getHighEntropyValues([
      'architecture',
      'bitness',
      'fullVersionList',
      'mobile',
      'model',
      'platform',
      'platformVersion',
    ]);

    const browser = preferredBrowser(high.fullVersionList ?? uaData.brands);
    const model = high.model?.trim() || fallback.device_model;
    const architecture = [high.architecture, high.bitness].filter(Boolean).join('-') || undefined;
    const reportedMobile = high.mobile ?? uaData.mobile;

    return {
      device_brand: inferBrand(model) ?? fallback.device_brand,
      device_model: model,
      device_type:
        reportedMobile == null
          ? fallback.device_type
          : reportedMobile
            ? 'mobile'
            : fallback.device_type,
      os_name: high.platform || uaData.platform || fallback.os_name,
      os_version: high.platformVersion || fallback.os_version,
      browser_name: browser?.brand || fallback.browser_name,
      browser_version: browser?.version || fallback.browser_version,
      architecture,
    };
  } catch {
    return fallback;
  }
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
    const device = await readDeviceDetails();
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
        ...device,
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
