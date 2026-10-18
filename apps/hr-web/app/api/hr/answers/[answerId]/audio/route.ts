import { ApiError } from "@/lib/api/server";
import { apiClient } from "@/lib/api/handler";
import { problemResponse } from "@/lib/api/error";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ answerId: string }> },
) {
  const { answerId } = await params;
  try {
    const upstream = await apiClient().requestRaw("GET", `/hr/answers/${answerId}/audio`);
    return new Response(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
      },
    });
  } catch (error) {
    if (error instanceof ApiError) return problemResponse(error.status, error.detail);
    throw error;
  }
}
