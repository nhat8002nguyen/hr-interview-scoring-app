"use client";

import { useState } from "react";
import { clientFetch } from "@/lib/api/client";
import type { ImportSummary } from "@/lib/contracts/types";
import { Button, Card } from "@/lib/components/ui";

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [summary, setSummary] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a data-pack zip first.");
      return;
    }

    setError(null);
    setSummary(null);
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const result = await clientFetch<ImportSummary>("/api/hr/import", {
        method: "POST",
        body: formData,
      });
      setSummary(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-xl p-6">
      <h1 className="mb-4 text-2xl font-semibold">Import data pack</h1>
      <Card>
        <form onSubmit={onSubmit} className="space-y-3">
          <input
            type="file"
            accept=".zip,application/zip"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm"
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" disabled={uploading}>
            {uploading ? "Importing..." : "Import"}
          </Button>
        </form>
      </Card>

      {summary && (
        <Card className="mt-4">
          <p className="mb-2 text-sm font-medium">Import complete</p>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            <dt className="text-slate-500">Roles created</dt>
            <dd>{summary.roles_created}</dd>
            <dt className="text-slate-500">Questions created</dt>
            <dd>{summary.questions_created}</dd>
            <dt className="text-slate-500">Candidates created</dt>
            <dd>{summary.candidates_created}</dd>
            <dt className="text-slate-500">Answers imported</dt>
            <dd>{summary.answers_imported}</dd>
            <dt className="text-slate-500">Scoring jobs queued</dt>
            <dd>{summary.scoring_jobs_queued}</dd>
            <dt className="text-slate-500">Audio needing a person</dt>
            <dd>{summary.audio_answers_needing_person}</dd>
          </dl>
        </Card>
      )}
    </main>
  );
}
