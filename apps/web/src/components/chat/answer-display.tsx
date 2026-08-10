"use client";

import { useId, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatTerminalData } from "@/hooks/use-chat-stream";
import type { components } from "@/lib/api/schema";
import { EvidenceCard } from "@/components/citations/evidence-card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type EvidenceCardModel = components["schemas"]["EvidenceCard"];

type AnswerDisplayProps = {
  type: "committed" | "refused";
  terminal: ChatTerminalData;
};

function EvidencePanel({
  evidence,
  activeId,
  onSelect,
}: {
  evidence: EvidenceCardModel[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  if (evidence.length === 0) return null;

  return (
    <section aria-label="Evidence" className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Evidence ({evidence.length})
      </h3>
      <ol className="space-y-2" role="list">
        {evidence.map((card) => (
          <li key={card.citation_id} id={`evidence-${card.citation_id}`}>
            <EvidenceCard evidence={card} />
          </li>
        ))}
      </ol>

      {/* Keyboard-accessible citation buttons that focus each evidence card */}
      <div
        role="group"
        aria-label="Jump to citation"
        className="flex flex-wrap gap-1.5 pt-1"
      >
        {evidence.map((card) => (
          <Button
            key={card.citation_id}
            variant={activeId === card.citation_id ? "default" : "outline"}
            size="xs"
            aria-label={`View evidence ${card.citation_id}: ${card.title}`}
            aria-pressed={activeId === card.citation_id}
            onClick={() => {
              onSelect(card.citation_id);
              document.getElementById(`evidence-${card.citation_id}`)?.scrollIntoView?.({
                behavior: "smooth",
                block: "nearest",
              });
            }}
          >
            {card.citation_id}
          </Button>
        ))}
      </div>
    </section>
  );
}

function TransparencyCollapse({ terminal }: { terminal: ChatTerminalData }) {
  const [open, setOpen] = useState(false);
  const id = useId();

  const trace = terminal.transparency.execution_trace ?? [];
  const errors = terminal.transparency.guardrail_errors ?? [];

  return (
    <details
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
      className="rounded border border-border text-xs"
    >
      <summary className="cursor-pointer select-none px-3 py-1.5 text-muted-foreground hover:text-foreground">
        Transparency {open ? "▲" : "▼"}
      </summary>
      <div id={id} className="space-y-1.5 p-3 pt-2">
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1">
          <dt className="text-foreground">Confidence</dt>
          <dd>{terminal.answer.confidence.toFixed(3)}</dd>
          {errors.length > 0 && (
            <>
              <dt className="text-foreground">Guardrail issues</dt>
              <dd>{errors.join(", ")}</dd>
            </>
          )}
        </dl>
        {trace.length > 0 && (
          <ol className="space-y-0.5 border-t border-border pt-2" aria-label="Execution trace">
            {trace.map((entry, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="w-4 text-right text-muted-foreground">{i + 1}.</span>
                <span className="font-mono">{(entry as { node?: string }).node ?? "?"}</span>
                <Badge variant="secondary" className="ml-auto h-4 text-[10px]">
                  {(entry as { status?: string }).status ?? ""}
                </Badge>
              </li>
            ))}
          </ol>
        )}
      </div>
    </details>
  );
}

/** Renders a committed answer or a refused result. Only shown after the terminal event arrives. */
export function AnswerDisplay({ type, terminal }: AnswerDisplayProps) {
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const { answer } = terminal;

  if (type === "refused") {
    return (
      <article className="space-y-3" data-testid="answer-display-refused">
        <header className="flex items-center gap-2">
          <Badge variant="secondary">Refusal</Badge>
          <span className="text-sm text-muted-foreground">
            The workflow could not ground a response for this query.
          </span>
        </header>

        {answer.refusal_reason && (
          <p className="rounded border border-border bg-muted/30 p-3 text-sm text-foreground">
            {answer.refusal_reason}
          </p>
        )}

        <p className="text-sm text-muted-foreground">
          Try rephrasing your question or providing more specific regulatory context.
        </p>

        <TransparencyCollapse terminal={terminal} />
      </article>
    );
  }

  return (
    <article className="space-y-4" data-testid="answer-display-committed">
      {/* Answer text — markdown, raw HTML disabled */}
      <div
        className={cn(
          "prose prose-sm max-w-none text-foreground",
          "[&_a]:text-primary [&_a]:underline-offset-4 [&_a:hover]:underline",
          "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-xs",
          "[&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-3",
        )}
        data-testid="answer-text"
      >
        <Markdown remarkPlugins={[remarkGfm]}>{answer.text}</Markdown>
      </div>

      {answer.evidence.length > 0 && (
        <EvidencePanel
          evidence={answer.evidence}
          activeId={activeEvidenceId}
          onSelect={setActiveEvidenceId}
        />
      )}

      <TransparencyCollapse terminal={terminal} />
    </article>
  );
}
