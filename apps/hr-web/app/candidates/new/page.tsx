"use client";

import { useState } from "react";
import { clientFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { CandidateDetail, Role } from "@/lib/contracts/types";
import { createCandidateSchema } from "@/lib/validation/schemas";
import { Button, Card, Select } from "@/lib/components/ui";
import { CopyButton } from "@/lib/components/CopyButton";

export default function NewCandidatePage() {
  const { data: roles } = useApiQuery<Role[]>("/api/hr/roles");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<CandidateDetail | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const parsed = createCandidateSchema.safeParse({
      name,
      email,
      role_id: Number(roleId),
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input");
      return;
    }

    setSubmitting(true);
    try {
      const result = await clientFetch<CandidateDetail>("/api/hr/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed.data),
      });
      setCreated(result);
      setName("");
      setEmail("");
      setRoleId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create candidate");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Add candidate</h1>
      <Card>
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Role</span>
            <Select
              value={roleId}
              onChange={(event) => setRoleId(event.target.value)}
              required
            >
              <option value="">Select a role</option>
              {roles?.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </Select>
          </label>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={submitting}>
            {submitting ? "Creating..." : "Create candidate"}
          </Button>
        </form>
      </Card>

      {created && (
        <Card className="mt-4">
          <p className="text-sm font-medium">Candidate created</p>
          <p className="mt-1 text-sm text-slate-600">
            {created.name} · {created.email}
          </p>
          <div className="mt-3 flex items-center gap-2">
            <code className="truncate rounded bg-slate-100 px-2 py-1 text-xs">
              {created.interview_link}
            </code>
            <CopyButton value={created.interview_link} />
          </div>
        </Card>
      )}
    </main>
  );
}
