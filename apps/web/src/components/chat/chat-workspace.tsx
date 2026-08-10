"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api/client";
import { useChatStream } from "@/hooks/use-chat-stream";
import { ChatComposer } from "@/components/chat/chat-composer";
import { StreamProgress } from "@/components/chat/stream-progress";
import { AnswerDisplay } from "@/components/chat/answer-display";
import { TurnList } from "@/components/chat/turn-list";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { ExportControls } from "@/components/summaries/export-controls";

type ChatWorkspaceProps = {
  sessionId: string;
};

function useSessionHistory(sessionId: string) {
  return useQuery({
    queryKey: ["sessions", sessionId, "turns"],
    queryFn: () => createApiClient().listSessionTurns(sessionId),
    staleTime: 60_000,
  });
}

export function ChatWorkspace({ sessionId }: ChatWorkspaceProps) {
  const router = useRouter();
  const qc = useQueryClient();
  const { state, isStreaming, submit, cancel, reset } = useChatStream();
  const [draft, setDraft] = useState("");
  const answerRef = useRef<HTMLDivElement>(null);

  const {
    data: historyData,
    isLoading: historyLoading,
    isError: historyError,
  } = useSessionHistory(sessionId);

  // On terminal (committed/refused): invalidate queries and update route.
  useEffect(() => {
    if (state.status !== "committed" && state.status !== "refused") return;
    const resolvedSessionId = state.sessionId;
    void qc.invalidateQueries({ queryKey: ["sessions", sessionId, "turns"] });
    void qc.invalidateQueries({ queryKey: ["sessions"] });
    // Update route to the resolved session id (may differ from URL if session was auto-created).
    if (resolvedSessionId && resolvedSessionId !== sessionId) {
      router.replace(`/chat/${resolvedSessionId}`);
    }
    // Clear the draft only on success.
    setDraft("");
    // Scroll answer into view.
    answerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [state.status, state, sessionId, qc, router]);

  const handleSubmit = useCallback(
    (query: string) => {
      // Reset any prior terminal state before starting a new request.
      reset();
      submit({
        query,
        sessionId,
        onSessionResolved(newId) {
          if (newId !== sessionId) {
            router.replace(`/chat/${newId}`);
          }
        },
      });
    },
    [submit, reset, sessionId, router],
  );

  const handleCancel = useCallback(() => {
    // Draft is preserved — only the streaming state resets.
    cancel();
  }, [cancel]);

  const turns = historyData?.turns ?? [];

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Header */}
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h1 className="text-base font-semibold">Research Session</h1>
          <Badge variant="outline" className="font-mono text-[10px]">
            {sessionId.slice(0, 8)}
          </Badge>
        </div>
        <ExportControls
          target={{ kind: "transcript", sessionId, filenameHint: `transcript-${sessionId}.txt` }}
          actionLabel="Export transcript"
          disabled={turns.length === 0}
        />
      </header>

      {/* History */}
      <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border bg-card p-4">
        {historyLoading && (
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}

        {historyError && (
          <p className="text-sm text-destructive">Failed to load session history.</p>
        )}

        {!historyLoading && !historyError && (
          <TurnList turns={turns} />
        )}

        {/* Live streaming area */}
        {(isStreaming || state.status === "committed" || state.status === "refused") && (
          <div className="mt-4 space-y-3 border-t border-border pt-4">
            {/* Current user query (shown immediately for feedback) */}
            {isStreaming && state.status === "streaming" && (
              <p className="text-sm font-medium text-foreground">
                {/* Query shown in composer — progress only here */}
              </p>
            )}

            {/* Progress — no answer text until terminal */}
            {isStreaming && state.status === "streaming" && (
              <StreamProgress
                nodes={state.nodes}
                latestNode={state.nodes.at(-1)}
              />
            )}

            {/* Terminal answer — only after committed/refused */}
            {(state.status === "committed" || state.status === "refused") && (
              <div ref={answerRef}>
                <AnswerDisplay type={state.status} terminal={state.terminal} />
              </div>
            )}
          </div>
        )}

        {state.status === "error" && (
          <div
            role="alert"
            className={cn(
              "mt-4 rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm",
            )}
          >
            <p className="font-medium text-destructive">Request failed</p>
            <p className="text-muted-foreground">{state.error.message}</p>
            <p className="mt-1 text-xs text-muted-foreground">Your query is preserved — you can try again.</p>
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="rounded-lg border border-border bg-card p-3">
        <ChatComposer
          draft={draft}
          onDraftChange={setDraft}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
}
