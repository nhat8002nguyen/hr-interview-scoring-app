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

export function InterviewFlow({ token }: InterviewFlowProps) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [interview, setInterview] = useState<InterviewResponse | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [submit, setSubmit] = useState<SubmitState>("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [lastUnchanged, setLastUnchanged] = useState(false);

  useEffect(() => {
    let active = true;

    getInterview(token)
      .then((data) => {
        if (!active) return;
        setInterview(data);

        const total = data.questions.length;
        const stored = localStorage.getItem(storageKey(token));
        const parsed = stored === null ? Number.NaN : Number(stored);
        const storedValid =
          Number.isInteger(parsed) && parsed >= 0 && parsed < total;

        if (storedValid) {
          setCurrentIndex(parsed);
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
        if (error instanceof ApiError && error.status === 401) {
          setPhase("invalid-link");
        } else {
          setPhase("error");
        }
      });

    return () => {
      active = false;
    };
  }, [token]);

  const goTo = useCallback(
    (index: number) => {
      setCurrentIndex(index);
      localStorage.setItem(storageKey(token), String(index));
    },
    [token],
  );

  const question = interview?.questions[currentIndex] ?? null;

  async function handleSubmitText(questionId: number, text: string) {
    setSubmit("submitting");
    setSubmitError(null);
    try {
      const result = await submitTextAnswer(token, questionId, text);
      setLastUnchanged(result.unchanged);
      setSubmit("received");
    } catch {
      setSubmitError("Your answer could not be submitted. Please try again.");
      setSubmit("error");
    }
  }

  async function handleSubmitAudio(questionId: number, file: File) {
    setSubmit("submitting");
    setSubmitError(null);
    try {
      const result = await submitAudioAnswer(token, questionId, file);
      setLastUnchanged(result.unchanged);
      setSubmit("received");
    } catch {
      setSubmitError("Your answer could not be submitted. Please try again.");
      setSubmit("error");
    }
  }

  async function handleContinue() {
    try {
      const updated = await getInterview(token);
      setInterview(updated);
      if (currentIndex + 1 >= updated.questions.length) {
        setPhase("complete");
      } else {
        goTo(currentIndex + 1);
      }
      setSubmit("idle");
      setSubmitError(null);
    } catch {
      setSubmitError("Your answer could not be submitted. Please try again.");
      setSubmit("error");
    }
  }

  if (phase === "loading") return <Loading />;
  if (phase === "invalid-link") return <InvalidLink />;
  if (phase === "error") {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="text-sm text-red-700">
          Something went wrong. Please try again.
        </p>
      </main>
    );
  }
  if (phase === "complete") return <Completion />;

  if (!interview || !question) return <Loading />;

  if (submit === "received") {
    return (
      <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center p-8">
        <Confirmation unchanged={lastUnchanged} onContinue={handleContinue} />
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
        submitting={submit === "submitting"}
        onSubmitText={handleSubmitText}
        onSubmitAudio={handleSubmitAudio}
      />
      {submitError && <p className="text-sm text-red-700">{submitError}</p>}
      <button
        type="button"
        onClick={() => goTo(Math.max(0, currentIndex - 1))}
        disabled={currentIndex === 0}
        className="self-start text-sm text-zinc-600 underline disabled:opacity-40"
      >
        Previous
      </button>
    </main>
  );
}
