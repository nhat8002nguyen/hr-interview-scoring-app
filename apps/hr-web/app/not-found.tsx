import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-xl flex-col items-start gap-3 p-6">
      <h1 className="text-2xl font-semibold">Not found</h1>
      <p className="text-sm text-slate-600">That page or record does not exist.</p>
      <Link href="/roles" className="text-sm font-medium text-slate-900 underline">
        Back to roles
      </Link>
    </main>
  );
}
