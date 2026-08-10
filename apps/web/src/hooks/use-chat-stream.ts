"use client";

import { useCallback, useRef, useState } from "react";
import { createApiClient } from "@/lib/api/client";
import type { ChatNodeData, ChatTerminalData } from "@/lib/api/sse";
import { isApiClientError } from "@/lib/api/errors";

export type { ChatNodeData, ChatTerminalData };

export type ChatStreamState =
  | { status: "idle" }
  | { status: "streaming"; sessionId: string | null; nodes: ChatNodeData[] }
  | {
      status: "committed";
      sessionId: string;
      nodes: ChatNodeData[];
      terminal: ChatTerminalData;
    }
  | {
      status: "refused";
      sessionId: string;
      nodes: ChatNodeData[];
      terminal: ChatTerminalData;
    }
  | { status: "error"; error: Error };

type SubmitOptions = {
  query: string;
  sessionId?: string | null;
  filters?: Record<string, string>;
  /** Called with the backend-assigned session id as soon as the started event arrives. */
  onSessionResolved?: (sessionId: string) => void;
};

export type UseChatStreamReturn = {
  state: ChatStreamState;
  isStreaming: boolean;
  submit: (opts: SubmitOptions) => void;
  cancel: () => void;
  reset: () => void;
};

const IDLE: ChatStreamState = { status: "idle" };

export function useChatStream(): UseChatStreamReturn {
  const [state, setState] = useState<ChatStreamState>(IDLE);
  const controllerRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    // Cancellation is not an error — return to idle with no synthetic answer.
    setState(IDLE);
  }, []);

  const reset = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setState(IDLE);
  }, []);

  const submit = useCallback((opts: SubmitOptions) => {
    // Abort any prior request.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setState({ status: "streaming", sessionId: opts.sessionId ?? null, nodes: [] });

    void (async () => {
      const client = createApiClient();
      try {
        const handle = await client.openChatStream(
          {
            query: opts.query,
            session_id: opts.sessionId ?? null,
            filters: opts.filters ?? {},
          },
          { signal: controller.signal },
        );

        for await (const event of handle.events) {
          if (event.type === "started") {
            opts.onSessionResolved?.(event.data.session_id);
            setState((prev) =>
              prev.status === "streaming"
                ? { ...prev, sessionId: event.data.session_id }
                : prev,
            );
          } else if (event.type === "node") {
            setState((prev) =>
              prev.status === "streaming"
                ? { ...prev, nodes: [...prev.nodes, event.data] }
                : prev,
            );
          } else if (event.type === "committed") {
            if (controllerRef.current === controller) {
              setState((previous) => ({
                status: "committed",
                sessionId: event.data.session_id,
                nodes: previous.status === "streaming" ? previous.nodes : [],
                terminal: event.data,
              }));
            }
            return;
          } else if (event.type === "refused") {
            if (controllerRef.current === controller) {
              setState((previous) => ({
                status: "refused",
                sessionId: event.data.session_id,
                nodes: previous.status === "streaming" ? previous.nodes : [],
                terminal: event.data,
              }));
            }
            return;
          } else if (event.type === "error") {
            if (controllerRef.current === controller) {
              setState({ status: "error", error: new Error(event.data.message) });
            }
            return;
          }
          // "done" — loop will exit after the parser yields it.
        }
      } catch (err) {
        // Cancellation is deliberate — return to idle, no synthetic answer.
        if (isApiClientError(err) && err.isCanceled) {
          if (controllerRef.current === controller) {
            setState(IDLE);
          }
          return;
        }
        if (controllerRef.current === controller) {
          setState({
            status: "error",
            error: err instanceof Error ? err : new Error("Stream failed unexpectedly."),
          });
        }
      }
    })();
  }, []);

  return {
    state,
    isStreaming: state.status === "streaming",
    submit,
    cancel,
    reset,
  };
}
