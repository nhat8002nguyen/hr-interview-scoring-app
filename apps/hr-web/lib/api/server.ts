export type HttpMethod = "GET" | "POST" | "PATCH";

export interface ApiRequestInit {
  body?: unknown;
  formData?: FormData;
}

export interface SessionStore {
  getAccessToken(): Promise<string | null>;
  getRefreshToken(): Promise<string | null>;
  setTokens(access: string, refresh: string): Promise<void>;
  clear(): Promise<void>;
}

export interface ApiClient {
  request<T>(method: HttpMethod, path: string, init?: ApiRequestInit): Promise<T>;
  requestRaw(method: HttpMethod, path: string, init?: ApiRequestInit): Promise<Response>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

async function extractDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string; title?: string };
    return data.detail ?? data.title ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export function createApiClient(store: SessionStore, baseUrl: string): ApiClient {
  let refreshInFlight: Promise<void> | null = null;

  async function refresh(staleToken: string | null): Promise<void> {
    // Another caller may already have rotated the token while this request
    // was in flight. If so, the retry will pick up the new token for free.
    if ((await store.getAccessToken()) !== staleToken) return;

    if (!refreshInFlight) {
      refreshInFlight = doRefresh().finally(() => {
        refreshInFlight = null;
      });
    }
    await refreshInFlight;
  }

  async function doRefresh(): Promise<void> {
    const refreshToken = await store.getRefreshToken();
    if (!refreshToken) {
      throw new ApiError(401, "Session expired");
    }
    const response = await fetch(`${baseUrl}/auth/refresh-tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) {
      await store.clear();
      throw new ApiError(response.status, "Session expired");
    }
    const data = (await response.json()) as RefreshResponse;
    await store.setTokens(data.access_token, data.refresh_token);
  }

  async function send(
    method: HttpMethod,
    path: string,
    init?: ApiRequestInit,
  ): Promise<Response> {
    const accessToken = await store.getAccessToken();
    const headers: Record<string, string> = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

    let body: BodyInit | undefined;
    if (init?.formData) {
      body = init.formData;
    } else if (init?.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(init.body);
    }

    return fetch(`${baseUrl}${path}`, { method, headers, body });
  }

  async function requestRaw(
    method: HttpMethod,
    path: string,
    init?: ApiRequestInit,
  ): Promise<Response> {
    const tokenUsed = await store.getAccessToken();
    let response = await send(method, path, init);

    // Only a request that carried a token can be recovered by refreshing.
    // Sign-in, which carries none, surfaces the upstream 401 unchanged.
    if (response.status === 401 && tokenUsed) {
      await refresh(tokenUsed);
      response = await send(method, path, init);
    }

    if (!response.ok) {
      throw new ApiError(response.status, await extractDetail(response));
    }

    return response;
  }

  async function request<T>(
    method: HttpMethod,
    path: string,
    init?: ApiRequestInit,
  ): Promise<T> {
    const response = await requestRaw(method, path, init);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return { request, requestRaw };
}
