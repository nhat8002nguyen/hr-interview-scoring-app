import type { ProblemDetails } from "@/lib/contracts/types";

export class ClientError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ClientError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ClientFetchOptions {
  /** Defaults to true. Set false for auth endpoints where 401 means bad credentials. */
  redirectOn401?: boolean;
}

export async function clientFetch<T>(
  path: string,
  init?: RequestInit,
  options?: ClientFetchOptions,
): Promise<T> {
  const response = await fetch(path, init);

  if (response.status === 401 && options?.redirectOn401 !== false) {
    if (typeof window !== "undefined") {
      window.location.assign("/sign-in");
    }
    throw new ClientError(401, "Session expired");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as Partial<ProblemDetails>;
      detail = body.detail ?? body.title ?? detail;
    } catch {
      // Keep the status text when the body is not JSON.
    }
    throw new ClientError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
