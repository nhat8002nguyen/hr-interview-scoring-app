"use client";

import type { AnswerType } from "@/lib/types";

export interface SegmentedControlProps {
  name: string;
  value: AnswerType;
  onChange: (value: AnswerType) => void;
}

const options: { value: AnswerType; label: string }[] = [
  { value: "text", label: "Type" },
  { value: "audio", label: "Upload audio" },
];

export function SegmentedControl({
  name,
  value,
  onChange,
}: SegmentedControlProps) {
  return (
    <div
      role="group"
      aria-label="Answer type"
      className="inline-flex gap-4 rounded-md border border-zinc-300 p-2"
    >
      {options.map((option) => (
        <label
          key={option.value}
          className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700"
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="h-4 w-4 accent-zinc-900"
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
