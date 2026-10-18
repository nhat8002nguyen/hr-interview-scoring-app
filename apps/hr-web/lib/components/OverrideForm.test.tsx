import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OverrideForm } from "./OverrideForm";

describe("OverrideForm", () => {
  it("does not submit when the reason is empty", async () => {
    const onSubmit = vi.fn();
    render(<OverrideForm onSubmit={onSubmit} disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: /override/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/reason is required/i)).toBeInTheDocument();
  });

  it("submits a valid score and reason", async () => {
    const onSubmit = vi.fn();
    render(<OverrideForm onSubmit={onSubmit} disabled={false} />);
    await userEvent.selectOptions(screen.getByLabelText(/score/i), "4");
    await userEvent.type(screen.getByLabelText(/reason/i), "Measured impact.");
    await userEvent.click(screen.getByRole("button", { name: /override/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      final_score: 4,
      override_reason: "Measured impact.",
    });
  });
});
