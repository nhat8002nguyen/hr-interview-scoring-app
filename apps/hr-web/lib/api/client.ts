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

export async function clientFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);

  if (response.status === 401) {
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
