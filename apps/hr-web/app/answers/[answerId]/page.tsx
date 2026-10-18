"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { clientFetch } from "@/lib/api/client";
import { useApiQuery } from "@/lib/hooks/useApiQuery";
import type { AnswerDetail } from "@/lib/contracts/types";
import { Card, Spinner } from "@/lib/components/ui";
import { ScoringBadge } from "@/lib/components/ScoringBadge";
import { OverrideForm, type OverrideValue } from "@/lib/components/OverrideForm";

export default function AnswerDetailPage() {
  const params = useParams<{ answerId: string }>();
  const { data: answer, error, loading, refetch } = useApiQuery<AnswerDetail>(
    `/api/hr/answers/${params.answerId}`,
  );
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canOverride =
    answer?.scoring.status === "scored" || answer?.scoring.status === "needs_a_person";

  async function handleOverride(value: OverrideValue) {
    setFormError(null);
    setSubmitting(true);
    try {
      await clientFetch<AnswerDetail>(`/api/hr/answers/${params.answerId}/score`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(value),
      });
      refetch();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not save the score");
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <main className="mx-auto w-full max-w-3xl p-6">
        <p className="text-sm text-red-600">{error}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-3xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Answer</h1>
      {loading && <Spinner />}
      {answer && (
        <div className="space-y-4">
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-slate-500">{answer.question_code}</span>
              <span className="flex items-center gap-2 text-sm text-slate-600">
                version {answer.version} · submitted{" "}
                {new Date(answer.submitted_at).toLocaleString()}
                <ScoringBadge
                  status={answer.scoring.status}
                  score={answer.scoring.final_score ?? answer.scoring.suggested_score}
                />
              </span>
            </div>
            <p className="mt-2 font-medium">{answer.question_prompt}</p>

            <div className="mt-3">
              <p className="mb-1 text-sm font-medium text-slate-500">Grading guide</p>
              <ul className="space-y-1 text-sm text-slate-700">
                {Object.entries(answer.grading_guide)
                  .sort(([a], [b]) => Number(a) - Number(b))
                  .map(([score, text]) => (
                    <li key={score}>
                      <span className="font-medium">{score}:</span> {text}
                    </li>
                  ))}
              </ul>
            </div>

            <div className="mt-4">
              <p className="mb-1 text-sm font-medium text-slate-500">
                {answer.answer_type === "audio" ? "Audio answer" : "Transcript"}
              </p>
              {answer.answer_type === "audio" ? (
                <audio controls src={`/api/hr/answers/${answer.id}/audio`} className="w-full" />
              ) : (
                <p className="whitespace-pre-wrap text-sm text-slate-800">{answer.text}</p>
              )}
            </div>
          </Card>

          <Card>
            <p className="text-sm font-medium text-slate-500">Suggested score</p>
            <div className="mt-1 flex items-center gap-2">
              <ScoringBadge
                status={answer.scoring.status}
                score={answer.scoring.suggested_score}
              />
              <span className="text-sm">Final: {answer.scoring.final_score ?? "not set"}</span>
            </div>
            {answer.scoring.suggested_reasoning && (
              <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                {answer.scoring.suggested_reasoning}
              </p>
            )}
            {answer.scoring.override_reason && (
              <p className="mt-2 text-sm text-slate-700">
                <span className="font-medium">Override reason:</span>{" "}
                {answer.scoring.override_reason}
              </p>
            )}
            {answer.scoring.last_error && (
              <p className="mt-2 text-sm text-red-600">Error: {answer.scoring.last_error}</p>
            )}
          </Card>

          <Card>
            <p className="mb-2 text-sm font-medium text-slate-500">Override score</p>
            {canOverride ? (
              <>
                <OverrideForm onSubmit={handleOverride} disabled={submitting} />
                {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
              </>
            ) : (
              <p className="text-sm text-slate-500">
                This answer is {answer.scoring.status.replace("_", " ")} and cannot be overridden
                yet.
              </p>
            )}
          </Card>
        </div>
      )}
    </main>
  );
}
