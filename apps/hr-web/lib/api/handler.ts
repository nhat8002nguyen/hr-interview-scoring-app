import { NextResponse } from "next/server";
import { ApiError, createApiClient, type ApiClient } from "@/lib/api/server";
import { problemResponse } from "@/lib/api/error";
import { createNextSessionStore } from "@/lib/auth/session";

export function apiClient(): ApiClient {
  return createApiClient(createNextSessionStore(), process.env.API_ORIGIN ?? "");
}

export async function jsonResult<T>(
  run: (client: ApiClient) => Promise<T>,
  status = 200,
): Promise<NextResponse> {
  try {
    const result = await run(apiClient());
    return NextResponse.json(result, { status });
  } catch (error) {
    if (error instanceof ApiError) return problemResponse(error.status, error.detail);
    throw error;
  }
}
