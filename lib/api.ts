import { ApiError } from "./types";
import type {
  InterviewResponse,
  ProblemDetails,
  SubmitResponse,
} from "./types";

export { ApiError } from "./types";

const API_ORIGIN = process.env.NEXT_PUBLIC_API_ORIGIN ?? "";

function tokenHeaders(token: string): Record<string, string> {
  return { "X-Candidate-Token": token };
}

async function request<T>(response: Promise<Response>): Promise<T> {
  const res = await response;

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = (await res.json()) as ProblemDetails;
      detail = body.detail;
    } catch {
      // A non-JSON error body leaves detail undefined.
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

export async function getInterview(token: string): Promise<InterviewResponse> {
  return request(
    fetch(`${API_ORIGIN}/candidate/interview`, { headers: tokenHeaders(token) }),
  );
}

export async function submitTextAnswer(
  token: string,
  questionId: number,
  text: string,
): Promise<SubmitResponse> {
  return request(
    fetch(`${API_ORIGIN}/candidate/interview/answers/${questionId}`, {
      method: "POST",
      headers: {
        ...tokenHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ answer_type: "text", text }),
    }),
  );
}

export async function submitAudioAnswer(
  token: string,
  questionId: number,
  file: File,
): Promise<SubmitResponse> {
  const form = new FormData();
  form.append("file", file);

  return request(
    fetch(`${API_ORIGIN}/candidate/interview/answers/${questionId}/audio`, {
      method: "POST",
      headers: tokenHeaders(token),
      body: form,
    }),
  );
}
