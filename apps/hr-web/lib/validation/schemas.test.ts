import { describe, expect, it } from "vitest";
import { overrideScoreSchema, createCandidateSchema, signInSchema } from "./schemas";

describe("overrideScoreSchema", () => {
  it("accepts a score in 1..4 with a non-empty reason", () => {
    expect(
      overrideScoreSchema.safeParse({ final_score: 4, override_reason: "Measured impact." }).success,
    ).toBe(true);
  });
  it("rejects a score below 1", () => {
    expect(overrideScoreSchema.safeParse({ final_score: 0, override_reason: "x" }).success).toBe(false);
  });
  it("rejects a score above 4", () => {
    expect(overrideScoreSchema.safeParse({ final_score: 5, override_reason: "x" }).success).toBe(false);
  });
  it("rejects a non-integer score", () => {
    expect(overrideScoreSchema.safeParse({ final_score: 3.5, override_reason: "x" }).success).toBe(false);
  });
  it("rejects a whitespace-only reason", () => {
    expect(overrideScoreSchema.safeParse({ final_score: 3, override_reason: "   " }).success).toBe(false);
  });
});

describe("createCandidateSchema", () => {
  it("rejects an invalid email", () => {
    expect(
      createCandidateSchema.safeParse({ name: "Nhi Tran", email: "nope", role_id: 1 }).success,
    ).toBe(false);
  });
  it("rejects a non-positive role_id", () => {
    expect(
      createCandidateSchema.safeParse({ name: "Nhi Tran", email: "a@b.com", role_id: 0 }).success,
    ).toBe(false);
  });
});

describe("signInSchema", () => {
  it("rejects an empty password", () => {
    expect(signInSchema.safeParse({ email: "hr@talotrace.ai", password: "" }).success).toBe(false);
  });
});
