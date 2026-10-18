import { NextResponse, type NextRequest } from "next/server";
import { ApiError, createApiClient } from "@/lib/api/server";
import { problemResponse } from "@/lib/api/error";
import { createNextSessionStore } from "@/lib/auth/session";
import type { AuthResponse } from "@/lib/contracts/types";
import { signInSchema } from "@/lib/validation/schemas";

export async function POST(request: NextRequest) {
  let raw: unknown;
  try {
    raw = await request.json();
  } catch {
    return problemResponse(400, "Malformed JSON body");
  }

  const parsed = signInSchema.safeParse(raw);
  if (!parsed.success) {
    return problemResponse(422, parsed.error.issues[0]?.message ?? "Invalid input");
  }

  try {
    const store = createNextSessionStore();
    const client = createApiClient(
      store,
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000",
    );
    const auth = await client.request<AuthResponse>("POST", "/auth/sign-in", {
      body: parsed.data,
    });
    await store.setTokens(auth.access_token, auth.refresh_token);
    return NextResponse.json({ user: auth.user });
  } catch (error) {
    if (error instanceof ApiError) {
      return problemResponse(error.status, error.detail);
    }
    throw error;
  }
}
