import { useEffect, useState } from "react";
import type { WeatherSnapshot } from "./observations";
import { getJson } from "./types";

export function useObservations(source: string, enabled: boolean) {
  const [result, setResult] = useState<{
    key: string;
    data: WeatherSnapshot | null;
    error: string;
  } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = source + "#" + attempt;
  useEffect(() => {
    if (!enabled || !source) return;
    const ctrl = new AbortController();
    void getJson<WeatherSnapshot>(
      "/api/observations",
      { run: source },
      ctrl.signal,
    )
      .then((data) => {
        if (!ctrl.signal.aborted) setResult({ key, data, error: "" });
      })
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted)
          setResult({
            key,
            data: null,
            error:
              err instanceof Error
                ? err.message
                : "Observations are unavailable.",
          });
      });
    return () => ctrl.abort();
  }, [enabled, source, key]);
  const current = result?.key === key ? result : null;
  return {
    data: enabled ? (current?.data ?? null) : null,
    error: current?.error ?? "",
    loading: enabled && !current,
    retry: () => setAttempt((v) => v + 1),
  };
}
