export const API_BASE_URL =
  import.meta.env.VITE_MEDICORE_API_BASE_URL?.replace(/\/$/, '') ?? '';

export class ApiClientError extends Error {
  status: number;
  statusText: string;
  body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    super(`API request failed with ${status} ${statusText}`);
    this.name = 'ApiClientError';
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

const buildUrl = (path: string) => {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
};

const parseResponseBody = async (response: Response) => {
  if (response.status === 204) {
    return undefined;
  }

  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    return response.json();
  }

  return response.text();
};

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });

  const body = await parseResponseBody(response);

  if (!response.ok) {
    throw new ApiClientError(response.status, response.statusText, body);
  }

  return body as T;
};

export const apiClient = {
  get<T>(path: string): Promise<T> {
    return request<T>(path, { method: 'GET' });
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
};
