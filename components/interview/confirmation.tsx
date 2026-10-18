import { Button } from "@/components/ui/button";

export interface ConfirmationProps {
  unchanged: boolean;
  onContinue: () => void;
}

export function Confirmation({ unchanged, onContinue }: ConfirmationProps) {
  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-6">
        <p className="text-lg font-semibold text-emerald-900">
          Your answer has been received
        </p>
        {unchanged && (
          <p className="mt-2 text-sm text-emerald-800">
            No changes to your previous answer.
          </p>
        )}
      </div>
      <Button type="button" onClick={onContinue}>
        Continue
      </Button>
    </section>
  );
}
