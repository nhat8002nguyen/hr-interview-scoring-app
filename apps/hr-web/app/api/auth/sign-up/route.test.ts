import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

vi.mock("@/lib/api/server", () => {
  class ApiError extends Error {
    readonly status: number;
    readonly detail: string;
    constructor(status: number, detail: string) {
      super(detail);
      this.name = "ApiError";
      this.status = status;
      this.detail = detail;
    }
  }
  return {
    ApiError,
    createApiClient: vi.fn(),
  };
});

vi.mock("@/lib/auth/session", () => ({
  createNextSessionStore: vi.fn(),
}));

import { ApiError, createApiClient } from "@/lib/api/server";
import { createNextSessionStore } from "@/lib/auth/session";
import { POST } from "./route";

const user = { id: 2, email: "newhr@example.com", role: "hr" } as const;

function signUpRequest() {
  return new NextRequest("http://localhost/api/auth/sign-up", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "newhr@example.com", password: "password123" }),
  });
}

describe("POST /api/auth/sign-up", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sets the auth tokens and returns the user on success", async () => {
    const setTokens = vi.fn();
    vi.mocked(createNextSessionStore).mockReturnValue({
      getAccessToken: vi.fn().mockResolvedValue(null),
      getRefreshToken: vi.fn().mockResolvedValue(null),
      setTokens,
      clear: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(createApiClient).mockReturnValue({
      request: vi.fn().mockResolvedValue({
        user,
        access_token: "access-token",
        refresh_token: "refresh-token",
      }),
      requestRaw: vi.fn(),
    });

    const res = await POST(signUpRequest());

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ user });
    expect(setTokens).toHaveBeenCalledWith("access-token", "refresh-token");
  });

  it("maps a 409 duplicate email to a problem response", async () => {
    vi.mocked(createNextSessionStore).mockReturnValue({
      getAccessToken: vi.fn().mockResolvedValue(null),
      getRefreshToken: vi.fn().mockResolvedValue(null),
      setTokens: vi.fn().mockResolvedValue(undefined),
      clear: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(createApiClient).mockReturnValue({
      request: vi.fn().mockRejectedValue(new ApiError(409, "email already registered")),
      requestRaw: vi.fn(),
    });

    const res = await POST(signUpRequest());

    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({
      type: "about:blank",
      title: "Conflict",
      status: 409,
      detail: "email already registered",
    });
  });

  it("maps a 422 invalid input to a problem response", async () => {
    vi.mocked(createNextSessionStore).mockReturnValue({
      getAccessToken: vi.fn().mockResolvedValue(null),
      getRefreshToken: vi.fn().mockResolvedValue(null),
      setTokens: vi.fn().mockResolvedValue(undefined),
      clear: vi.fn().mockResolvedValue(undefined),
    });
    vi.mocked(createApiClient).mockReturnValue({
      request: vi.fn().mockRejectedValue(new ApiError(422, "password is too short")),
      requestRaw: vi.fn(),
    });

    const res = await POST(signUpRequest());

    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({
      type: "about:blank",
      title: "Unprocessable Entity",
      status: 422,
      detail: "password is too short",
    });
  });

  it("rejects a short password before calling the API", async () => {
    const request = new NextRequest("http://localhost/api/auth/sign-up", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "newhr@example.com", password: "short" }),
    });

    const res = await POST(request);

    expect(res.status).toBe(422);
    expect(createApiClient).not.toHaveBeenCalled();
  });
});
