import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Confirmation } from "@/components/interview/confirmation";

it("renders the received message and continue", async () => {
  const user = userEvent.setup();
  const onContinue = vi.fn();
  render(<Confirmation unchanged={false} onContinue={onContinue} />);
  expect(
    screen.getByText("Your answer has been received"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(onContinue).toHaveBeenCalled();
});

it("notes when the submission was unchanged", () => {
  render(<Confirmation unchanged onContinue={vi.fn()} />);
  expect(
    screen.getByText("No changes to your previous answer."),
  ).toBeInTheDocument();
});
