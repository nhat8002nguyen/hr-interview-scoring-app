import { cookies } from "next/headers";
import type { SessionStore } from "@/lib/api/server";

export const ACCESS_COOKIE_NAME = "hr_access";
export const REFRESH_COOKIE_NAME = "hr_refresh";

const COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
};

export function createNextSessionStore(): SessionStore {
  return {
    async getAccessToken() {
      const store = await cookies();
      return store.get(ACCESS_COOKIE_NAME)?.value ?? null;
    },
    async getRefreshToken() {
      const store = await cookies();
      return store.get(REFRESH_COOKIE_NAME)?.value ?? null;
    },
    async setTokens(access, refresh) {
      const store = await cookies();
      store.set(ACCESS_COOKIE_NAME, access, COOKIE_OPTIONS);
      store.set(REFRESH_COOKIE_NAME, refresh, COOKIE_OPTIONS);
    },
    async clear() {
      const store = await cookies();
      store.delete(ACCESS_COOKIE_NAME);
      store.delete(REFRESH_COOKIE_NAME);
    },
  };
}
