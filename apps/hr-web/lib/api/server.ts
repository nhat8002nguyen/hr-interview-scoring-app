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

interface RefreshedTokens {
  access: string;
  refresh: string;
}

interface RefreshResponse {
  access_token: string;
  refresh_token: string;
}

// Module-scoped so every route handler's client shares one rotation per
// session. Keyed by the refresh token so concurrent requests from the same
// browser coalesce without conflating different sessions.
const refreshInFlight = new Map<string, Promise<RefreshedTokens>>();

async function extractDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: string; title?: string };
    return data.detail ?? data.title ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export function createApiClient(store: SessionStore, baseUrl: string): ApiClient {
  async function doRefresh(refreshToken: string): Promise<RefreshedTokens> {
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
    return { access: data.access_token, refresh: data.refresh_token };
  }

  async function refresh(staleToken: string): Promise<RefreshedTokens> {
    // Another request may already have rotated this request's cookie view.
    const current = await store.getAccessToken();
    if (current && current !== staleToken) {
      const refreshToken = await store.getRefreshToken();
      return { access: current, refresh: refreshToken ?? "" };
    }

    const refreshToken = await store.getRefreshToken();
    if (!refreshToken) {
      throw new ApiError(401, "Session expired");
    }

    let pending = refreshInFlight.get(refreshToken);
    if (!pending) {
      pending = doRefresh(refreshToken).finally(() => {
        refreshInFlight.delete(refreshToken);
      });
      refreshInFlight.set(refreshToken, pending);
    }
    return pending;
  }

  async function send(
    method: HttpMethod,
    path: string,
    init: ApiRequestInit | undefined,
    accessToken: string | null,
  ): Promise<Response> {
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
    let response = await send(method, path, init, tokenUsed);

    // Only a request that carried a token can be recovered by refreshing.
    // Sign-in, which carries none, surfaces the upstream 401 unchanged.
    if (response.status === 401 && tokenUsed) {
      const refreshed = await refresh(tokenUsed);
      response = await send(method, path, init, refreshed.access);
    }

    if (!response.ok) {
      throw new ApiError(response.status, await extractDetail(response));
    }

    return response;
  }

  async function request<T>(method: HttpMethod, path: string, init?: ApiRequestInit): Promise<T> {
    const response = await requestRaw(method, path, init);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return { request, requestRaw };
}
