"use client";

import { Button } from "@/lib/components/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col items-start gap-3 p-6">
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="text-sm text-slate-600">{error.message || "An unexpected error occurred."}</p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
