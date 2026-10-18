import type { NextRequest } from "next/server";
import { jsonResult } from "@/lib/api/handler";
import type { ScoringJob } from "@/lib/contracts/types";

export async function GET(request: NextRequest) {
  const status = request.nextUrl.searchParams.get("status");
  const path = status
    ? `/hr/scoring-jobs?status=${encodeURIComponent(status)}`
    : "/hr/scoring-jobs";
  return jsonResult((client) => client.request<ScoringJob[]>("GET", path));
}
