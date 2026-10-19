"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api/client";

export function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  if (pathname === "/sign-in") return null;

  async function signOut() {
    await clientFetch("/api/auth/sign-out", { method: "POST" }).catch(() => undefined);
    router.push("/sign-in");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex w-full max-w-4xl items-center gap-4 p-4 text-sm">
        <Link href="/roles" className="font-semibold">
          Talotrace HR
        </Link>
        <Link href="/roles" className="text-slate-600 hover:underline">
          Roles
        </Link>
        <Link href="/candidates/new" className="text-slate-600 hover:underline">
          Add candidate
        </Link>
        <Link href="/scoring-jobs" className="text-slate-600 hover:underline">
          Scoring jobs
        </Link>
        <Link href="/import" className="text-slate-600 hover:underline">
          Import
        </Link>
        <button onClick={signOut} className="ml-auto text-slate-600 hover:underline">
          Sign out
        </button>
      </nav>
    </header>
  );
}
