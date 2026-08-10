"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";

type SearchRequest = components["schemas"]["SearchRequest"];
type SearchResponse = components["schemas"]["SearchResponse"];

type UseSearchQueryArgs = {
  request: SearchRequest;
  enabled: boolean;
  resource: "research" | "search";
};

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((entry) => stableStringify(entry)).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  return `{${entries
    .map(([key, entry]) => `${JSON.stringify(key)}:${stableStringify(entry)}`)
    .join(",")}}`;
}

function useCurrentUserId(): string | null {
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    try {
      const supabase = createSupabaseBrowserClient();
      void supabase.auth.getSession().then(({ data }) => {
        if (active) {
          setUserId(data.session?.user.id ?? null);
        }
      });

      const subscription = supabase.auth.onAuthStateChange((_event, session) => {
        if (active) {
          setUserId(session?.user.id ?? null);
        }
      });

      return () => {
        active = false;
        subscription.data.subscription.unsubscribe();
      };
    } catch {
      return () => {
        active = false;
      };
    }
  }, []);

  return userId;
}

export function useSearchQuery(args: UseSearchQueryArgs) {
  const apiClient = useMemo(() => createApiClient(), []);
  const userId = useCurrentUserId();

  return useQuery<SearchResponse>({
    queryKey: [
      "api",
      "search",
      args.resource,
      userId ?? "anonymous",
      stableStringify(args.request),
    ],
    queryFn: ({ signal }) => apiClient.search(args.request, { signal }),
    enabled: args.enabled && args.request.query.trim().length > 0,
    retry: false,
  });
}
