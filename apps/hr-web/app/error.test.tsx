import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorPage from "./error";

describe("ErrorPage", () => {
  it("shows the error and retries", async () => {
    const reset = vi.fn();
    render(<ErrorPage error={new Error("boom")} reset={reset} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(reset).toHaveBeenCalledTimes(1);
  });
});
