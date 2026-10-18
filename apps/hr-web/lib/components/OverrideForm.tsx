"use client";

import { useState } from "react";
import { overrideScoreSchema } from "@/lib/validation/schemas";
import { Button, Select, Textarea } from "./ui";

export interface OverrideValue {
  final_score: number;
  override_reason: string;
}

export function OverrideForm({
  onSubmit,
  disabled,
}: {
  onSubmit: (value: OverrideValue) => void;
  disabled: boolean;
}) {
  const [score, setScore] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!reason.trim()) {
      setError("Reason is required.");
      return;
    }

    const parsed = overrideScoreSchema.safeParse({
      final_score: Number(score),
      override_reason: reason,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Invalid input");
      return;
    }

    setError(null);
    onSubmit(parsed.data);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Score</span>
        <Select value={score} onChange={(event) => setScore(event.target.value)} disabled={disabled}>
          <option value="">Select a score</option>
          {[1, 2, 3, 4].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
      </label>
      <label className="block text-sm">
        <span className="mb-1 block font-medium">Reason</span>
        <Textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          disabled={disabled}
        />
      </label>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <Button type="submit" disabled={disabled}>
        Override score
      </Button>
    </form>
  );
}
