import { type NextRequest } from "next/server";
import { jsonResult } from "@/lib/api/handler";
import { problemResponse } from "@/lib/api/error";
import type { AnswerDetail } from "@/lib/contracts/types";
import { overrideScoreSchema } from "@/lib/validation/schemas";

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ answerId: string }> },
) {
  const { answerId } = await params;

  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return problemResponse(400, "Malformed JSON body");
  }

  const parsed = overrideScoreSchema.safeParse(raw);
  if (!parsed.success) {
    return problemResponse(422, parsed.error.issues[0]?.message ?? "Invalid input");
  }

  return jsonResult((client) =>
    client.request<AnswerDetail>("PATCH", `/hr/answers/${answerId}/score`, {
      body: parsed.data,
    }),
  );
}
