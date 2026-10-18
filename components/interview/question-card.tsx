import type { Question } from "@/lib/types";
import { AnswerInput } from "./answer-input";
import { Progress } from "./progress";

export interface QuestionCardProps {
  question: Question;
  index: number;
  total: number;
  submitting: boolean;
  onSubmitText: (questionId: number, text: string) => void;
  onSubmitAudio: (questionId: number, file: File) => void;
}

export function QuestionCard({
  question,
  index,
  total,
  submitting,
  onSubmitText,
  onSubmitAudio,
}: QuestionCardProps) {
  return (
    <section className="space-y-6">
      <Progress index={index} total={total} />
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {question.code}
        </p>
        <h2 className="text-xl font-semibold text-zinc-900">
          {question.prompt}
        </h2>
      </div>
      <AnswerInput
        questionId={question.id}
        initialAnswer={question.answer}
        submitting={submitting}
        onSubmitText={onSubmitText}
        onSubmitAudio={onSubmitAudio}
      />
    </section>
  );
}
