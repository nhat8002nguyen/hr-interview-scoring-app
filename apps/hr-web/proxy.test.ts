import { describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

function request(path: string, cookie?: string) {
  return new NextRequest(`http://localhost${path}`, cookie ? { headers: { cookie } } : undefined);
}

describe("proxy", () => {
  it("redirects to /sign-in when the access cookie is absent", () => {
    const res = proxy(request("/roles"));
    expect(res.status).toBe(307);
    expect(new URL(res.headers.get("location")!).pathname).toBe("/sign-in");
  });

  it("allows the request through when the access cookie is present", () => {
    const res = proxy(request("/roles", "hr_access=tok"));
    expect(res.status).toBe(200);
    expect(res.headers.get("location")).toBeNull();
  });

  it("leaves /sign-in, /sign-up and /api unguarded", () => {
    for (const path of ["/sign-in", "/sign-up", "/api/hr/roles"]) {
      const res = proxy(request(path));
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    }
  });
});
