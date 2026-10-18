import { NextResponse } from "next/server";
import { createApiClient } from "@/lib/api/server";
import { createNextSessionStore } from "@/lib/auth/session";

export async function POST() {
  const store = createNextSessionStore();
  const refreshToken = await store.getRefreshToken();
  const client = createApiClient(
    store,
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000",
  );

  try {
    await client.request("POST", "/auth/sign-out", {
      body: { refresh_token: refreshToken },
    });
  } catch {
    // The local session is cleared even if the upstream revoke fails.
  }

  await store.clear();
  return new NextResponse(null, { status: 204 });
}
