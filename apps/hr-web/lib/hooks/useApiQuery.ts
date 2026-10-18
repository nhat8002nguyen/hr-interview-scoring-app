"use client";

import { useEffect, useState } from "react";
import { clientFetch } from "@/lib/api/client";

export interface ApiQueryState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function useApiQuery<T>(path: string): ApiQueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    clientFetch<T>(path)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [path]);

  return { data, error, loading };
}
