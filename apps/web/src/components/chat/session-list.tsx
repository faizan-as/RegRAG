"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PlusIcon, MessageSquareTextIcon } from "lucide-react";
import { createApiClient } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(new Date(value));
  } catch {
    return "";
  }
}

type SessionListProps = {
  activeSessionId?: string;
  /** Called with the new session id after creation succeeds. */
  onSessionCreated?: (sessionId: string) => void;
};

export function SessionList({ activeSessionId, onSessionCreated }: SessionListProps) {
  const [offset, setOffset] = useState(0);
  const qc = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["sessions", { limit: PAGE_SIZE, offset }],
    queryFn: () => createApiClient().listSessions({ limit: PAGE_SIZE, offset }),
  });

  const createMutation = useMutation({
    mutationFn: () => createApiClient().createSession({}),
    onSuccess(session) {
      void qc.invalidateQueries({ queryKey: ["sessions"] });
      onSessionCreated?.(session.session_id);
    },
  });

  const sessions = data?.sessions ?? [];
  const hasPrev = offset > 0;
  const hasNext = sessions.length === PAGE_SIZE;

  return (
    <aside aria-label="Sessions" className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Sessions
        </p>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          aria-label="New conversation"
          title="New conversation"
        >
          <PlusIcon className="size-3.5" />
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-1.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full rounded" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-xs text-destructive">Failed to load sessions.</p>
      )}

      {!isLoading && !isError && sessions.length === 0 && (
        <p className="text-xs text-muted-foreground">No sessions yet.</p>
      )}

      <ul className="space-y-0.5" role="list">
        {sessions.map((session) => {
          const active = session.session_id === activeSessionId;
          return (
            <li key={session.session_id}>
              <Link
                href={`/chat/${session.session_id}`}
                className={cn(
                  "flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm transition-colors",
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                <MessageSquareTextIcon className="size-3.5 shrink-0" aria-hidden />
                <span className="flex-1 truncate">
                  {session.title ?? "Untitled session"}
                </span>
                <Badge variant="outline" className="h-4 shrink-0 text-[10px]">
                  {formatDate(session.created_at)}
                </Badge>
              </Link>
            </li>
          );
        })}
      </ul>

      {(hasPrev || hasNext) && (
        <div className="flex justify-between gap-2 pt-1">
          <Button
            variant="ghost"
            size="xs"
            disabled={!hasPrev}
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            aria-label="Previous page of sessions"
          >
            ← Prev
          </Button>
          <Button
            variant="ghost"
            size="xs"
            disabled={!hasNext}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            aria-label="Next page of sessions"
          >
            Next →
          </Button>
        </div>
      )}
    </aside>
  );
}
