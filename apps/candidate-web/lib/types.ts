export type AnswerType = "text" | "audio";

export interface Candidate {
  id: number;
  name: string | null;
  role: string;
}

export interface Answer {
  answer_type: AnswerType;
  text: string | null;
  version: number;
  submitted_at: string;
}

export interface Question {
  id: number;
  code: string;
  sort_order: number;
  prompt: string;
  answer: Answer | null;
}

export interface Progress {
  answered: number;
  total: number;
}

export interface InterviewResponse {
  candidate: Candidate;
  questions: Question[];
  progress: Progress;
}

export interface SubmitResponse {
  status: "received";
  unchanged: boolean;
  answer: {
    answer_type: AnswerType;
    version: number;
    submitted_at: string;
  };
}

export interface ProblemDetails {
  type?: string;
  title?: string;
  status: number;
  detail?: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail?: string,
  ) {
    super(detail ?? `Request failed with status ${status}`);
    this.name = "ApiError";
  }
}
