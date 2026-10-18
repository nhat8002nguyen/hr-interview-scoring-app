import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InterviewFlow } from "@/components/interview/interview-flow";
import { getInterview, submitTextAnswer } from "@/lib/api";
import { ApiError } from "@/lib/types";
import type { InterviewResponse, Question } from "@/lib/types";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getInterview: vi.fn(),
    submitTextAnswer: vi.fn(),
    submitAudioAnswer: vi.fn(),
  };
});

const codes = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"];

function buildQuestions(answered: number[] = []): Question[] {
  return codes.map((code, index) => ({
    id: index + 1,
    code,
    sort_order: index + 1,
    prompt: code,
    answer: answered.includes(index)
      ? {
          answer_type: "text" as const,
          text: `${code} answer`,
          version: 1,
          submitted_at: "t",
        }
      : null,
  }));
}

function interview(answered: number[] = []): InterviewResponse {
  return {
    candidate: { id: 1, name: "Nhi", role: "Backend Engineer" },
    questions: buildQuestions(answered),
    progress: { answered: answered.length, total: 6 },
  };
}

const interviewWithFirstAnswered = () => interview([0]);
const interviewAllAnswered = () => interview([0, 1, 2, 3, 4, 5]);

beforeEach(() => {
  localStorage.clear();
  vi.resetAllMocks();
});

it("shows loading then the first question", async () => {
  let resolve!: (value: InterviewResponse) => void;
  vi.mocked(getInterview).mockReturnValue(
    new Promise<InterviewResponse>((r) => {
      resolve = r;
    }),
  );
  render(<InterviewFlow token="tok" />);
  expect(screen.getByText("Loading")).toBeInTheDocument();
  resolve(interview());
  expect(await screen.findByText("Question 1 of 6")).toBeInTheDocument();
});

it("shows invalid-link on a 401", async () => {
  vi.mocked(getInterview).mockRejectedValue(new ApiError(401, "not found"));
  render(<InterviewFlow token="tok" />);
  expect(
    await screen.findByText("This interview link is not valid."),
  ).toBeInTheDocument();
});

it("resumes at the stored question index", async () => {
  localStorage.setItem("talotrace:interview:tok:currentQuestion", "2");
  vi.mocked(getInterview).mockResolvedValue(interview());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 3 of 6")).toBeInTheDocument();
});

it("falls back to the first unanswered question when stored index is malformed", async () => {
  localStorage.setItem("talotrace:interview:tok:currentQuestion", "abc");
  vi.mocked(getInterview).mockResolvedValue(interviewWithFirstAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("shows completion when all questions are answered and nothing is stored", async () => {
  vi.mocked(getInterview).mockResolvedValue(interviewAllAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText(/complete/i)).toBeInTheDocument();
});

it("submits, confirms, and advances with a re-fetch", async () => {
  const user = userEvent.setup();
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitTextAnswer).mockResolvedValue({
    status: "received",
    unchanged: false,
    answer: { answer_type: "text", version: 1, submitted_at: "t" },
  });
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(
    await screen.findByText("Your answer has been received"),
  ).toBeInTheDocument();
  vi.mocked(getInterview).mockResolvedValue(interviewWithFirstAnswered());
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("shows an inline error when submit rejects", async () => {
  const user = userEvent.setup();
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitTextAnswer).mockRejectedValue(new Error("network down"));
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "x");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(await screen.findByText(/could not be submitted/i)).toBeInTheDocument();
});
