"use client";

import { useState } from "react";
import { clientFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { ScoringJob, ScoringStatus } from "@/lib/contracts/types";
import { Button, Card, Select, Spinner } from "@/lib/components/ui";
import { ScoringBadge } from "@/lib/components/ScoringBadge";

const STATUSES: ScoringStatus[] = ["queued", "scored", "failed", "needs_a_person"];

export default function ScoringJobsPage() {
  const [status, setStatus] = useState("");
  const path = status
    ? `/api/hr/scoring-jobs?status=${encodeURIComponent(status)}`
    : "/api/hr/scoring-jobs";
  const { data, error, loading, refetch } = useApiQuery<ScoringJob[]>(path);
  const [retrying, setRetrying] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  async function retry(jobId: number) {
    setActionError(null);
    setRetrying(jobId);
    try {
      await clientFetch(`/api/hr/scoring-jobs/${jobId}/retry`, { method: "POST" });
      refetch();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetrying(null);
    }
  }

  return (
    <main className="mx-auto w-full max-w-5xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Scoring jobs</h1>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-600">Status</span>
          <div className="w-48">
            <Select value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All</option>
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value.replace("_", " ")}
                </option>
              ))}
            </Select>
          </div>
        </label>
      </div>

      {loading && <Spinner />}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {actionError && <p className="mb-2 text-sm text-red-600">{actionError}</p>}

      {data && data.length === 0 && <p className="text-sm text-slate-500">No jobs.</p>}

      {data && data.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Candidate</th>
                <th className="px-4 py-2 font-medium">Question</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Attempts</th>
                <th className="px-4 py-2 font-medium">Last error</th>
                <th className="px-4 py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {data.map((job) => (
                <tr key={job.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">{job.candidate_name}</td>
                  <td className="px-4 py-2">{job.question_code}</td>
                  <td className="px-4 py-2">
                    <ScoringBadge status={job.status} />
                  </td>
                  <td className="px-4 py-2">{job.attempt_count}</td>
                  <td className="px-4 py-2 text-red-600">{job.last_error ?? ""}</td>
                  <td className="px-4 py-2">
                    {job.status === "failed" && (
                      <Button
                        onClick={() => retry(job.id)}
                        disabled={retrying === job.id}
                        className="px-2 py-1 text-xs"
                      >
                        {retrying === job.id ? "Retrying..." : "Retry"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </main>
  );
}
