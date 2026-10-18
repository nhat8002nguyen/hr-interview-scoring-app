"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { CandidateSummary } from "@/lib/contracts/types";
import { Card, Spinner } from "@/lib/components/ui";
import { ScoringBadge } from "@/lib/components/ScoringBadge";

export default function RoleCandidatesPage() {
  const params = useParams<{ roleId: string }>();
  const { data, error, loading } = useApiQuery<CandidateSummary[]>(
    `/api/hr/roles/${params.roleId}/candidates`,
  );

  return (
    <main className="mx-auto w-full max-w-4xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Candidates</h1>
      {loading && <Spinner />}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-slate-500">No candidates for this role.</p>
      )}
      <ul className="space-y-3">
        {data?.map((candidate) => (
          <li key={candidate.id}>
            <Card>
              <div className="flex items-center justify-between">
                <Link href={`/candidates/${candidate.id}`} className="font-medium hover:underline">
                  {candidate.name}
                </Link>
                <span className="text-sm text-slate-500">
                  {candidate.answer_progress.answered}/{candidate.answer_progress.total} answered
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-3">
                {candidate.answers.map((answer) => (
                  <span
                    key={answer.id}
                    className="inline-flex items-center gap-1 text-xs text-slate-600"
                  >
                    {answer.question_code}
                    <ScoringBadge
                      status={answer.scoring.status}
                      score={answer.scoring.final_score ?? answer.scoring.suggested_score}
                    />
                  </span>
                ))}
              </div>
            </Card>
          </li>
        ))}
      </ul>
    </main>
  );
}
