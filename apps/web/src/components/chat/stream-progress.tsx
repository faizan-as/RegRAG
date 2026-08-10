import type { ChatNodeData } from "@/hooks/use-chat-stream";
import { nodeLabelFor } from "@/components/chat/node-labels";
import { Skeleton } from "@/components/ui/skeleton";

type StreamProgressProps = {
  nodes: ChatNodeData[];
  latestNode?: ChatNodeData;
};

/** Safe progress panel shown while streaming. Never exposes answer text. */
export function StreamProgress({ nodes, latestNode }: StreamProgressProps) {
  const currentLabel = latestNode ? nodeLabelFor(latestNode.node) : "Starting…";
  const completedNodes = latestNode ? nodes.slice(0, -1) : nodes;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="false"
      aria-label="Workflow progress"
      className="space-y-3 py-2"
    >
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span className="inline-block size-2 animate-pulse rounded-full bg-primary" aria-hidden />
        <span>{currentLabel}</span>
      </div>

      {completedNodes.length > 0 && (
        <ol className="space-y-1 border-l border-border pl-3" aria-label="Completed steps">
          {completedNodes.map((node, idx) => (
            <li key={idx} className="flex items-baseline gap-2 text-xs text-muted-foreground">
              <span
                className="inline-block size-1.5 shrink-0 translate-y-px rounded-full bg-primary/60"
                aria-hidden
              />
              <span>{nodeLabelFor(node.node)}</span>
              {node.evidence_count != null && node.evidence_count > 0 && (
                <span className="ml-auto shrink-0 tabular-nums">
                  {node.evidence_count} result{node.evidence_count !== 1 ? "s" : ""}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}

      {/* Skeleton preview – no answer text */}
      <div className="space-y-2 pt-1" aria-hidden>
        <Skeleton className="h-3 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}
