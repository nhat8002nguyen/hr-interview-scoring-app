import type { ScoringStatus } from "@/lib/contracts/types";
import { Badge } from "./ui";

const STYLES: Record<ScoringStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  scored: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  needs_a_person: "bg-amber-100 text-amber-900",
};

const LABELS: Record<ScoringStatus, string> = {
  queued: "Queued",
  scored: "Scored",
  failed: "Failed",
  needs_a_person: "Needs a person",
};

export function ScoringBadge({
  status,
  score,
}: {
  status: ScoringStatus;
  score?: number | null;
}) {
  const text = status === "scored" && score != null ? String(score) : LABELS[status];
  return (
    <Badge
      className={STYLES[status]}
      aria-label={status === "scored" && score != null ? `Score ${score}` : LABELS[status]}
    >
      {text}
    </Badge>
  );
}
