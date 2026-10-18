"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getInterview,
  submitAudioAnswer,
  submitTextAnswer,
} from "@/lib/api";
import type { InterviewResponse } from "@/lib/types";
import { Completion } from "./completion";
import { Confirmation } from "./confirmation";
import { InvalidLink } from "./invalid-link";
import { Loading } from "./loading";
import { QuestionCard } from "./question-card";

export interface InterviewFlowProps {
  token: string;
}

type Phase = "loading" | "invalid-link" | "error" | "ready" | "complete";
type SubmitState = "idle" | "submitting" | "received" | "error";

function storageKey(token: string): string {
  return `talotrace:interview:${token}:currentQuestion`;
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function InterviewFlow({ token }: InterviewFlowProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [interview, setInterview] = useState<InterviewResponse | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [submit, setSubmit] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [advanceError, setAdvanceError] = useState<string | null>(null);
  const [lastUnchanged, setLastUnchanged] = useState(false);

  useEffect(() => {
    let active = true;

    getInterview(token)
      .then((data) => {
        if (!active) return;
        setInterview(data);

        const total = data.questions.length;
        const stored = localStorage.getItem(storageKey(token));
        const storedValid =
          stored !== null && /^\d+$/.test(stored) && Number(stored) < total;

        if (storedValid) {
          setCurrentIndex(Number(stored));
          setPhase("ready");
          return;
        }

        const firstUnanswered = data.questions.findIndex(
          (question) => question.answer === null,
        );

        if (firstUnanswered === -1) {
          setPhase("complete");
          return;
        }

        setCurrentIndex(firstUnanswered);
        setPhase("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setPhase(isUnauthorized(error) ? "invalid-link" : "error");
      });

    return () => {
      active = false;
    };
  }, [token]);

  const goTo = useCallback(
    (index: number) => {
      setCurrentIndex(index);
      setSubmitError(null);
      setSubmit((current) => (current === "error" ? "idle" : current));
      localStorage.setItem(storageKey(token), String(index));
    },
    [token],
  );

  const clearStoredIndex = useCallback(() => {
    localStorage.removeItem(storageKey(token));
  }, [token]);

  const question = interview?.questions[currentIndex] ?? null;
  const isLast = interview
    ? currentIndex === interview.questions.length - 1
    : true;
  const submitting = submit === "submitting";

  async function submitAnswer(
    request: () => Promise<{ unchanged: boolean }>,
  ): Promise<void> {
    setSubmit("submitting");
    setSubmitError(null);
    setAdvanceError(null);
    try {
      const result = await request();
      setLastUnchanged(result.unchanged);
      setSubmit("received");
    } catch (error) {
      if (isUnauthorized(error)) {
        setPhase("invalid-link");
        return;
      }
      setSubmitError("Your answer could not be submitted. Please try again.");
      setSubmit("error");
    }
  }

  function handleSubmitText(questionId: number, text: string) {
    return submitAnswer(() => submitTextAnswer(token, questionId, text));
  }

  function handleSubmitAudio(questionId: number, file: File) {
    return submitAnswer(() => submitAudioAnswer(token, questionId, file));
  }

  async function handleContinue() {
    setAdvanceError(null);
    try {
      const updated = await getInterview(token);
      setInterview(updated);
      if (currentIndex + 1 >= updated.questions.length) {
        clearStoredIndex();
        setPhase("complete");
      } else {
        goTo(currentIndex + 1);
      }
      setSubmit("idle");
      setSubmitError(null);
    } catch (error) {
      if (isUnauthorized(error)) {
        setPhase("invalid-link");
        return;
      }
      // The answer was already saved; never regress to the form or lose the draft.
      setAdvanceError(
        "Your answer was received, but the next question could not be loaded. Please try again.",
      );
    }
  }

  if (phase === "loading") return <Loading />;
  if (phase === "invalid-link") return <InvalidLink />;
  if (phase === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p role="alert" className="text-sm text-red-700">
          Something went wrong. Please try again.
        </p>
      </main>
    );
  }
  if (phase === "complete") return <Completion />;

  if (!interview || !question) return <Loading />;

  if (submit === "received") {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-4 p-8">
        <Confirmation unchanged={lastUnchanged} onContinue={handleContinue} />
        {advanceError && (
          <p role="alert" className="text-sm text-red-700">
            {advanceError}
          </p>
        )}
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
      <QuestionCard
        key={question.id}
        question={question}
        index={currentIndex}
        total={interview.questions.length}
        submitting={submitting}
        onSubmitText={handleSubmitText}
        onSubmitAudio={handleSubmitAudio}
      />
      {submitError && (
        <p role="alert" className="text-sm text-red-700">
          {submitError}
        </p>
      )}
      <div className="flex gap-6">
        <button
          type="button"
          onClick={() => goTo(Math.max(0, currentIndex - 1))}
          disabled={currentIndex === 0 || submitting}
          className="self-start text-sm text-zinc-600 underline disabled:opacity-40"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => !isLast && goTo(currentIndex + 1)}
          disabled={isLast || submitting}
          className="self-start text-sm text-zinc-600 underline disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </main>
  );
}
