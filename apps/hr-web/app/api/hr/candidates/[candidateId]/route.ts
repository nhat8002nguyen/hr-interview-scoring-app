import { jsonResult } from "@/lib/api/handler";
import type { CandidateDetail } from "@/lib/contracts/types";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ candidateId: string }> },
) {
  const { candidateId } = await params;
  return jsonResult((client) =>
    client.request<CandidateDetail>("GET", `/hr/candidates/${candidateId}`),
  );
}
