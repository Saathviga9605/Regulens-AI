import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../services/apiClient";

export interface ApiQuery<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

/** Runs an API call when `key` changes; ignores out-of-order responses. */
export function useApiQuery<T>(load: () => Promise<T>, key: string): ApiQuery<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  const run = useCallback(() => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    loadRef.current()
      .then((result) => {
        if (id === seq.current) setData(result);
      })
      .catch((err: unknown) => {
        if (id === seq.current) setError(err instanceof ApiError ? err.message : "Unexpected error while loading data.");
      })
      .finally(() => {
        if (id === seq.current) setLoading(false);
      });
  }, []);

  useEffect(run, [run, key]);

  return { data, error, loading, reload: run, setData };
}
