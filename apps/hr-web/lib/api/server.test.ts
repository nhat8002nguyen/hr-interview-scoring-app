import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./server";
import type { SessionStore } from "./server";

function memoryStore(access?: string, refresh?: string): SessionStore {
  let a = access ?? null;
  let r = refresh ?? null;
  return {
    getAccessToken: async () => a,
    getRefreshToken: async () => r,
    setTokens: async (na, nr) => {
      a = na;
      r = nr;
    },
    clear: async () => {
      a = null;
      r = null;
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createApiClient", () => {
  it("attaches the bearer token and returns the JSON body", async () => {
    const store = memoryStore("tok");
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient(store, "http://api");
    const out = await client.request<{ id: number }>("GET", "/hr/roles");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/hr/roles",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok" }),
      }),
    );
    expect(out).toEqual({ id: 1 });
  });

  it("refreshes once and retries on 401", async () => {
    const store = memoryStore("expired", "refresh-token");
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({}), { status: 401 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ access_token: "new-access", refresh_token: "new-refresh" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 1 }]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient(store, "http://api");
    const out = await client.request<{ id: number }[]>("GET", "/hr/roles");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(out).toEqual([{ id: 1 }]);
    expect(await store.getAccessToken()).toBe("new-access");
  });

  it("throws ApiError with the problem detail on non-2xx", async () => {
    const store = memoryStore("tok");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "answer not found" }), { status: 404 })),
    );
    const client = createApiClient(store, "http://api");
    const error = await client.request("GET", "/hr/answers/999").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 404, detail: "answer not found" });
  });

  it("rotates the refresh token only once under concurrent 401s across clients", async () => {
    // In production every route handler builds its own client and its own
    // request-scoped session store, so two concurrent browser requests are
    // two clients sharing the same refresh cookie value.
    const storeA = memoryStore("expired", "refresh-token");
    const storeB = memoryStore("expired", "refresh-token");
    let refreshCalls = 0;
    let validAccess = "valid-token";
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "http://api/auth/refresh-tokens") {
        refreshCalls += 1;
        validAccess = "a" + refreshCalls;
        return new Response(
          JSON.stringify({ access_token: validAccess, refresh_token: "r" + refreshCalls }),
          { status: 200 },
        );
      }
      if (url === "http://api/hr/roles") {
        const auth = (init?.headers as Record<string, string> | undefined)?.Authorization;
        if (auth !== `Bearer ${validAccess}`) {
          return new Response(JSON.stringify({ detail: "expired" }), { status: 401 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 401 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const clientA = createApiClient(storeA, "http://api");
    const clientB = createApiClient(storeB, "http://api");
    await Promise.all([
      clientA.request("GET", "/hr/roles"),
      clientB.request("GET", "/hr/roles"),
    ]);
    expect(refreshCalls).toBe(1);
  });
});
