import { describe, expect, it } from "vitest";
import { problemResponse } from "./error";

describe("problemResponse", () => {
  it("returns an RFC 7807 body with the right status", async () => {
    const res = problemResponse(404, "answer not found");
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({
      type: "about:blank",
      title: "Not Found",
      status: 404,
      detail: "answer not found",
    });
  });

  it("maps an unknown status to a generic title", async () => {
    const res = problemResponse(500, "boom");
    expect(res.status).toBe(500);
    expect((await res.json()).title).toBe("Error");
  });
});
