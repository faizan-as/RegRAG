import type { components } from "@/lib/api/schema";
import { AnswerDisplay } from "@/components/chat/answer-display";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { ChatTerminalData } from "@/hooks/use-chat-stream";

type TurnResponse = components["schemas"]["TurnResponse"];

function buildTerminalFromTurn(turn: TurnResponse): ChatTerminalData {
  return {
    session_id: turn.answer.session_id ?? "",
    turn_id: turn.turn_id,
    answer: turn.answer,
    transparency: {
      execution_trace: [],
      retrieval_diagnostics: {},
      provider_fallback_trace: [],
      ignored_filter_keys: [],
      guardrail_errors: [],
    },
  };
}

type TurnListProps = {
  turns: TurnResponse[];
};

function formatTimestamp(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

/** Renders immutable historical turns in chronological order. */
export function TurnList({ turns }: TurnListProps) {
  if (turns.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No turns yet. Ask a question to begin.
      </p>
    );
  }

  return (
    <ol className="space-y-6" aria-label="Conversation history">
      {turns.map((turn) => (
        <li key={turn.turn_id} className="space-y-3">
          {/* User query */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <Badge variant="outline" className="mt-0.5 shrink-0">
                You
              </Badge>
              <p className="text-sm">{turn.query}</p>
            </div>
            <time
              dateTime={turn.created_at}
              className="shrink-0 text-xs text-muted-foreground"
            >
              {formatTimestamp(turn.created_at)}
            </time>
          </div>

          {/* Answer */}
          <div className="ml-8">
            <AnswerDisplay
              type={turn.answer.refused ? "refused" : "committed"}
              terminal={buildTerminalFromTurn(turn)}
            />
          </div>

          <Separator />
        </li>
      ))}
    </ol>
  );
}
