import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnswerInput } from "@/components/interview/answer-input";

it("renders a textarea and a Type/Upload audio toggle", () => {
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={null}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Your answer")).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Type" })).toBeChecked();
});

it("prefills text from initialAnswer", () => {
  const answer = {
    answer_type: "text" as const,
    text: "previous",
    version: 1,
    submitted_at: "t",
  };
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={answer}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Your answer")).toHaveValue("previous");
});

it("disables submit while text is empty or whitespace", async () => {
  const user = userEvent.setup();
  render(
    <AnswerInput
      questionId={1}
      initialAnswer={null}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={vi.fn()}
    />,
  );
  const submit = screen.getByRole("button", { name: "Submit answer" });
  expect(submit).toBeDisabled();
  await user.type(screen.getByLabelText("Your answer"), "   ");
  expect(submit).toBeDisabled();
});

it("calls onSubmitText with the question id and text", async () => {
  const user = userEvent.setup();
  const onSubmitText = vi.fn();
  render(
    <AnswerInput
      questionId={3}
      initialAnswer={null}
      submitting={false}
      onSubmitText={onSubmitText}
      onSubmitAudio={vi.fn()}
    />,
  );
  await user.type(screen.getByLabelText("Your answer"), "my answer");
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(onSubmitText).toHaveBeenCalledWith(3, "my answer");
});

it("calls onSubmitAudio with the selected file", async () => {
  const user = userEvent.setup();
  const onSubmitAudio = vi.fn();
  render(
    <AnswerInput
      questionId={2}
      initialAnswer={null}
      submitting={false}
      onSubmitText={vi.fn()}
      onSubmitAudio={onSubmitAudio}
    />,
  );
  await user.click(screen.getByRole("radio", { name: "Upload audio" }));
  const file = new File(["x"], "a.m4a", { type: "audio/mp4" });
  await user.upload(screen.getByLabelText("Audio file"), file);
  await user.click(screen.getByRole("button", { name: "Submit answer" }));
  expect(onSubmitAudio).toHaveBeenCalledWith(2, file);
});
