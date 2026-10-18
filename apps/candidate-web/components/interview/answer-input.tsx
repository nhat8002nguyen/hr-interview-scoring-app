"use client";

import { useState } from "react";
import type { Answer, AnswerType } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Textarea } from "@/components/ui/textarea";

export interface AnswerInputProps {
  questionId: number;
  initialAnswer: Answer | null;
  submitting: boolean;
  onSubmitText: (questionId: number, text: string) => void;
  onSubmitAudio: (questionId: number, file: File) => void;
}

export function AnswerInput({
  questionId,
  initialAnswer,
  submitting,
  onSubmitText,
  onSubmitAudio,
}: AnswerInputProps) {
  const [mode, setMode] = useState<AnswerType>(
    initialAnswer?.answer_type ?? "text",
  );
  const [text, setText] = useState(
    initialAnswer?.answer_type === "text" ? (initialAnswer.text ?? "") : "",
  );
  const [file, setFile] = useState<File | null>(null);

  const canSubmit =
    !submitting && (mode === "text" ? text.trim() !== "" : file !== null);

  function handleSubmit() {
    if (!canSubmit) return;

    if (mode === "text") {
      onSubmitText(questionId, text);
    } else if (file) {
      onSubmitAudio(questionId, file);
    }
  }

  return (
    <div className="space-y-4">
      <SegmentedControl
        name={`answer-mode-${questionId}`}
        value={mode}
        onChange={setMode}
      />

      {mode === "text" ? (
        <Textarea
          aria-label="Your answer"
          rows={8}
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Type your answer here."
        />
      ) : (
        <div className="space-y-1">
          <input
            aria-label="Audio file"
            type="file"
            accept="audio/*"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-zinc-700 file:mr-4 file:rounded-md file:border-0 file:bg-zinc-100 file:px-4 file:py-2 file:text-sm file:font-medium hover:file:bg-zinc-200"
          />
          <p className="text-xs text-zinc-500">
            Upload a recording of your answer.
          </p>
        </div>
      )}

      <Button type="button" disabled={!canSubmit} onClick={handleSubmit}>
        Submit answer
      </Button>
    </div>
  );
}
