import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ScoringBadge } from "./ScoringBadge";

describe("ScoringBadge", () => {
  it("shows the score for scored", () => {
    render(<ScoringBadge status="scored" score={3} />);
    expect(screen.getByText("3")).toBeInTheDocument();
  });
  it('shows "failed" and no score for failed', () => {
    render(<ScoringBadge status="failed" score={undefined} />);
    expect(screen.getByText(/failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/^\d+$/)).toBeNull();
  });
  it('shows "needs a person" for needs_a_person', () => {
    render(<ScoringBadge status="needs_a_person" />);
    expect(screen.getByText(/needs a person/i)).toBeInTheDocument();
  });
  it('shows "queued" for queued', () => {
    render(<ScoringBadge status="queued" />);
    expect(screen.getByText(/queued|waiting/i)).toBeInTheDocument();
  });
});
