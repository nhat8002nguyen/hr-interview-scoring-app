export type ScoringStatus = "queued" | "scored" | "failed" | "needs_a_person";
export type AnswerType = "text" | "audio";
export type IamRole = "hr" | "admin" | "regular";

export type GradingGuide = Record<"1" | "2" | "3" | "4", string>;

export interface ProblemDetails {
  type?: string;
  title?: string;
  status: number;
  detail: string;
}

export interface User {
  id: number;
  email: string;
  role: IamRole;
}

export interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
}

export interface Role {
  id: number;
  name: string;
  candidate_count: number;
}

export interface ScoringSummary {
  status: ScoringStatus;
  suggested_score: number | null;
  final_score: number | null;
  override_reason: string | null;
}

export interface ScoringDetail {
  status: ScoringStatus;
  suggested_score: number | null;
  suggested_reasoning: string | null;
  final_score: number | null;
  override_reason: string | null;
  overridden_by: number | null;
  attempt_count: number;
  last_error: string | null;
  scored_at: string | null;
}

export interface AnswerSummary {
  id: number;
  question_id: number;
  question_code: string;
  answer_type: AnswerType;
  version: number;
  scoring: ScoringSummary;
}

export interface CandidateAnswer {
  id: number;
  question_id: number;
  question_code: string;
  answer_type: AnswerType;
  version: number;
  submitted_at: string;
  scoring: ScoringDetail;
}

export interface CandidateSummary {
  id: number;
  name: string;
  email: string;
  answer_progress: { answered: number; total: number };
  answers: AnswerSummary[];
}

export interface CandidateDetail {
  id: number;
  name: string;
  email: string;
  role_id: number;
  session_token: string;
  interview_link: string;
  answer_progress: { answered: number; total: number };
  answers: CandidateAnswer[];
}

export interface AnswerDetail {
  id: number;
  candidate_id: number;
  question_id: number;
  question_code: string;
  question_prompt: string;
  grading_guide: GradingGuide;
  answer_type: AnswerType;
  text: string | null;
  version: number;
  submitted_at: string;
  scoring: ScoringDetail;
}

export interface ScoringJob {
  id: number;
  answer_id: number;
  candidate_id: number;
  candidate_name: string;
  question_code: string;
  status: ScoringStatus;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
}

export interface ImportSummary {
  roles_created: number;
  questions_created: number;
  candidates_created: number;
  answers_imported: number;
  scoring_jobs_queued: number;
  audio_answers_needing_person: number;
}
