"use client";

import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, MessageSquareTextIcon } from "lucide-react";
import { createApiClient } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
  } catch {
    return "";
  }
}

export default function ChatPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["sessions", { limit: 50, offset: 0 }],
    queryFn: () => createApiClient().listSessions({ limit: 50, offset: 0 }),
  });

  const createMutation = useMutation({
    mutationFn: () => createApiClient().createSession({}),
    onSuccess(session) {
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      router.push(`/chat/${session.session_id}`);
    },
  });

  const sessions = data?.sessions ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Regulatory Chat</h1>
          <p className="text-sm text-muted-foreground">
            Citation-bound answers grounded in FDA guidance.
          </p>
        </div>
        <Button
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          aria-label="Start a new conversation"
        >
          <PlusIcon className="size-4" aria-hidden />
          New conversation
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {isError && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          Failed to load sessions.
        </p>
      )}

      {!isLoading && !isError && sessions.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <MessageSquareTextIcon className="mx-auto mb-3 size-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            No sessions yet. Start a new conversation to begin.
          </p>
        </div>
      )}

      {sessions.length > 0 && (
        <ul className="space-y-1.5" role="list" aria-label="Recent sessions">
          {sessions.map((session) => (
            <li key={session.session_id}>
              <button
                type="button"
                className="flex w-full items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
                onClick={() => router.push(`/chat/${session.session_id}`)}
                aria-label={`Open session: ${session.title ?? "Untitled session"}`}
              >
                <MessageSquareTextIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="flex-1 truncate text-sm">
                  {session.title ?? "Untitled session"}
                </span>
                <Badge
                  variant={session.status === "active" ? "secondary" : "outline"}
                  className="h-5 shrink-0 text-xs"
                >
                  {session.status}
                </Badge>
                <time
                  dateTime={session.created_at}
                  className="shrink-0 text-xs text-muted-foreground"
                >
                  {formatDate(session.created_at)}
                </time>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
