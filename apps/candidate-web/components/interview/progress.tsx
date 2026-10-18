export interface ProgressProps {
  index: number;
  total: number;
}

export function Progress({ index, total }: ProgressProps) {
  const percent = total > 0 ? Math.round(((index + 1) / total) * 100) : 0;

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-zinc-700">
        Question {index + 1} of {total}
      </p>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200">
        <div
          className="h-full rounded-full bg-zinc-900"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
