"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { CandidateDetail, Role } from "@/lib/contracts/types";
import { Card, Spinner } from "@/lib/components/ui";
import { ScoringBadge } from "@/lib/components/ScoringBadge";
import { CopyButton } from "@/lib/components/CopyButton";

export default function CandidateDetailPage() {
  const params = useParams<{ candidateId: string }>();
  const { data: candidate, error, loading } = useApiQuery<CandidateDetail>(
    `/api/hr/candidates/${params.candidateId}`,
  );
  const { data: roles } = useApiQuery<Role[]>("/api/hr/roles");

  const roleName = candidate
    ? (roles?.find((role) => role.id === candidate.role_id)?.name ?? `Role #${candidate.role_id}`)
    : "";

  return (
    <main className="mx-auto w-full max-w-4xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Candidate</h1>
      {loading && <Spinner />}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {candidate && (
        <>
          <Card className="mb-4">
            <p className="text-lg font-medium">{candidate.name}</p>
            <p className="text-sm text-slate-600">
              {candidate.email} · {roleName}
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="truncate rounded bg-slate-100 px-2 py-1 text-xs">
                {candidate.interview_link}
              </code>
              <CopyButton value={candidate.interview_link} />
            </div>
          </Card>

          {candidate.answers.length === 0 ? (
            <p className="text-sm text-slate-500">No answers yet.</p>
          ) : (
            <ul className="space-y-3">
              {candidate.answers.map((answer) => (
                <li key={answer.id}>
                  <Link href={`/answers/${answer.id}`}>
                    <Card className="flex items-center justify-between hover:border-slate-400">
                      <span className="font-medium">{answer.question_code}</span>
                      <span className="flex items-center gap-2 text-sm text-slate-600">
                        v{answer.version}
                        <ScoringBadge
                          status={answer.scoring.status}
                          score={
                            answer.scoring.final_score ?? answer.scoring.suggested_score
                          }
                        />
                      </span>
                    </Card>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
