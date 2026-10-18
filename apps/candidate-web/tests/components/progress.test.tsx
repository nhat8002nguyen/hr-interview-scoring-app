import { render, screen } from "@testing-library/react";
import { Progress } from "@/components/interview/progress";

it("renders the one-based position", () => {
  render(<Progress index={1} total={6} />);
  expect(screen.getByText("Question 2 of 6")).toBeInTheDocument();
});
