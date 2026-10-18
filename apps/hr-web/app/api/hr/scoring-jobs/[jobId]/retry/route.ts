import { jsonResult } from "@/lib/api/handler";
import type { ScoringJob } from "@/lib/contracts/types";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;
  return jsonResult((client) =>
    client.request<ScoringJob>("POST", `/hr/scoring-jobs/${jobId}/retry`),
  );
}
