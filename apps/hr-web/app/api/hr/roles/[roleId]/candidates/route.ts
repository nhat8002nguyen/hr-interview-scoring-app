import { jsonResult } from "@/lib/api/handler";
import type { CandidateSummary } from "@/lib/contracts/types";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ roleId: string }> },
) {
  const { roleId } = await params;
  return jsonResult((client) =>
    client.request<CandidateSummary[]>("GET", `/hr/roles/${roleId}/candidates`),
  );
}
