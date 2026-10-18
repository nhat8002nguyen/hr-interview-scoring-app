"use client";

import { useState } from "react";
import { Button } from "./ui";

export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard access can fail outside a secure context; ignore.
    }
  }

  return (
    <Button type="button" onClick={copy} className="bg-slate-600 hover:bg-slate-500">
      {copied ? "Copied" : "Copy link"}
    </Button>
  );
}
