"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDotIcon } from "lucide-react";
import { getPublicConfigState } from "@/lib/env";
import { cn } from "@/lib/utils";

export function ApiStatusIndicator() {
  const config = getPublicConfigState();

  const healthQuery = useQuery({
    queryKey: ["api-health", config.values.NEXT_PUBLIC_API_BASE_URL],
    enabled: config.isConfigured,
    queryFn: async () => {
      const response = await fetch(`${config.values.NEXT_PUBLIC_API_BASE_URL}/health`, {
        method: "GET",
        cache: "no-store",
      });
      return response.ok;
    },
    staleTime: 60_000,
    gcTime: 5 * 60_000,
    retry: 0,
  });

  const state = !config.isConfigured
    ? { label: "API unconfigured", tone: "muted" as const }
    : healthQuery.data
      ? { label: "API available", tone: "ok" as const }
      : healthQuery.isLoading
        ? { label: "Checking API", tone: "muted" as const }
        : { label: "API unavailable", tone: "warn" as const };

  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs text-muted-foreground",
        state.tone === "ok" && "border-success/50 text-foreground",
        state.tone === "warn" && "border-withdrawn/40 text-withdrawn",
      )}
      aria-live="polite"
    >
      <CircleDotIcon className="size-3.5" />
      {state.label}
    </span>
  );
}
