"use client";

import Link from "next/link";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { Role } from "@/lib/contracts/types";
import { Card, Spinner } from "@/lib/components/ui";

export default function RolesPage() {
  const { data, error, loading } = useApiQuery<Role[]>("/api/hr/roles");

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Roles</h1>
      {loading && <Spinner />}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-500">No roles yet. Import the data pack first.</p>
      )}
      <ul className="space-y-3">
        {data?.map((role) => (
          <li key={role.id}>
            <Link href={`/roles/${role.id}`}>
              <Card className="flex items-center justify-between hover:border-slate-400">
                <span className="font-medium">{role.name}</span>
                <span className="text-sm text-slate-500">{role.candidate_count} candidates</span>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
