import { type NextRequest } from "next/server";
import { jsonResult } from "@/lib/api/handler";
import { problemResponse } from "@/lib/api/error";
import type { CandidateDetail } from "@/lib/contracts/types";
import { createCandidateSchema } from "@/lib/validation/schemas";

export async function POST(request: NextRequest) {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return problemResponse(400, "Malformed JSON body");
  }

  const parsed = createCandidateSchema.safeParse(raw);
  if (!parsed.success) {
    return problemResponse(422, parsed.error.issues[0]?.message ?? "Invalid input");
  }

  return jsonResult(
    (client) => client.request<CandidateDetail>("POST", "/hr/candidates", { body: parsed.data }),
    201,
  );
}
