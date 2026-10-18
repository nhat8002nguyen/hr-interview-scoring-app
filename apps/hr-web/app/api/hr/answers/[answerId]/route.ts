import { jsonResult } from "@/lib/api/handler";
import type { AnswerDetail } from "@/lib/contracts/types";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ answerId: string }> },
) {
  const { answerId } = await params;
  return jsonResult((client) => client.request<AnswerDetail>("GET", `/hr/answers/${answerId}`));
}
