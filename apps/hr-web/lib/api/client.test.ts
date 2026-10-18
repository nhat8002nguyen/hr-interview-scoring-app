import { afterEach, describe, expect, it, vi } from "vitest";
import { ClientError, clientFetch } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("clientFetch", () => {
  it("returns parsed JSON on 2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 1 }), { status: 200 })),
    );
    await expect(clientFetch<{ id: number }>("/api/hr/roles")).resolves.toEqual({ id: 1 });
  });

  it("throws ClientError with the problem detail on non-2xx", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "oops" }), { status: 404 })),
    );
    const error = await clientFetch("/api/hr/answers/1").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ClientError);
    expect(error).toMatchObject({ status: 404, detail: "oops" });
  });
});
