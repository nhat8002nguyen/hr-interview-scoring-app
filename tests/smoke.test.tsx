import { render, screen } from "@testing-library/react";
import Page from "@/app/page";

it("renders the fallback message", () => {
  render(<Page />);
  expect(
    screen.getByText("Open the interview link you were sent"),
  ).toBeInTheDocument();
});
