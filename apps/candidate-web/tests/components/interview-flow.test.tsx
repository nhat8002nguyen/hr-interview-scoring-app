import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InterviewFlow } from "@/components/interview/interview-flow";
import {
  getInterview,
  submitAudioAnswer,
  submitTextAnswer,
} from "@/lib/api";
import { ApiError } from "@/lib/types";
import type { InterviewResponse, Question, SubmitResponse } from "@/lib/types";

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
const storageKey = "talotrace:interview:tok:currentQuestion";

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

const received: SubmitResponse = {
  status: "received",
  unchanged: false,
  answer: { answer_type: "text", version: 1, submitted_at: "t" },
};

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

it("shows a generic error when the initial load fails", async () => {
  vi.mocked(getInterview).mockRejectedValue(new TypeError("network down"));
  render(<InterviewFlow token="tok" />);
  expect(
    await screen.findByText("Something went wrong. Please try again."),
  ).toBeInTheDocument();
});

it("resumes at the stored question index", async () => {
  localStorage.setItem(storageKey, "2");
  vi.mocked(getInterview).mockResolvedValue(interview());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 3 of 6")).toBeInTheDocument();
});

it("falls back to the first unanswered question when stored index is malformed", async () => {
  localStorage.setItem(storageKey, "abc");
  vi.mocked(getInterview).mockResolvedValue(interviewWithFirstAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("treats an empty stored value as malformed", async () => {
  localStorage.setItem(storageKey, "");
  vi.mocked(getInterview).mockResolvedValue(interviewWithFirstAnswered());
  render(<InterviewFlow token="tok" />);
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
});

it("falls back when the stored index is out of range", async () => {
  localStorage.setItem(storageKey, "99");
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
  vi.mocked(submitTextAnswer).mockResolvedValue(received);
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

it("shows invalid-link when a submit returns 401", async () => {
  const user = userEvent.setup();
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitTextAnswer).mockRejectedValue(new ApiError(401, "expired"));
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "x");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(
    await screen.findByText("This interview link is not valid."),
  ).toBeInTheDocument();
});

it("keeps the confirmation when the continue refetch fails", async () => {
  const user = userEvent.setup();
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitTextAnswer).mockResolvedValue(received);
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  await screen.findByText("Your answer has been received");
  vi.mocked(getInterview).mockRejectedValue(new Error("network down"));
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(
    await screen.findByText("Your answer has been received"),
  ).toBeInTheDocument();
  expect(
    await screen.findByText(/next question could not be loaded/i),
  ).toBeInTheDocument();
});

it("shows completion after the last question and clears the stored index", async () => {
  const user = userEvent.setup();
  localStorage.setItem(storageKey, "5");
  vi.mocked(getInterview).mockResolvedValue(interview([0, 1, 2, 3, 4]));
  vi.mocked(submitTextAnswer).mockResolvedValue(received);
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 6 of 6");
  await user.type(screen.getByLabelText("Your answer"), "last answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  await screen.findByText("Your answer has been received");
  vi.mocked(getInterview).mockResolvedValue(interviewAllAnswered());
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByText(/completed all six/i)).toBeInTheDocument();
  expect(localStorage.getItem(storageKey)).toBeNull();
});

it("navigates back and forward between questions", async () => {
  const user = userEvent.setup();
  localStorage.setItem(storageKey, "2");
  vi.mocked(getInterview).mockResolvedValue(interview());
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 3 of 6");
  await user.click(screen.getByRole("button", { name: "Previous" }));
  expect(await screen.findByText("Question 2 of 6")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByText("Question 3 of 6")).toBeInTheDocument();
});

it("disables navigation while a submit is in flight", async () => {
  const user = userEvent.setup();
  let resolveSubmit!: (value: SubmitResponse) => void;
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitTextAnswer).mockReturnValue(
    new Promise<SubmitResponse>((r) => {
      resolveSubmit = r;
    }),
  );
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.type(screen.getByLabelText("Your answer"), "x");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  resolveSubmit(received);
  expect(
    await screen.findByText("Your answer has been received"),
  ).toBeInTheDocument();
});

it("shows an inline error when an audio upload is rejected", async () => {
  const user = userEvent.setup();
  vi.mocked(getInterview).mockResolvedValue(interview());
  vi.mocked(submitAudioAnswer).mockRejectedValue(
    new ApiError(422, "invalid file"),
  );
  render(<InterviewFlow token="tok" />);
  await screen.findByText("Question 1 of 6");
  await user.click(screen.getByRole("radio", { name: "Upload audio" }));
  await user.upload(
    screen.getByLabelText("Audio file"),
    new File(["x"], "a.m4a", { type: "audio/mp4" }),
  );
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(await screen.findByText(/could not be submitted/i)).toBeInTheDocument();
});
