/** Human-readable label for each LangGraph node name. */
const NODE_LABELS: Record<string, string> = {
  query_understand: "Understanding query",
  retrieval_router: "Routing retrieval",
  hybrid_retrieve: "Searching guidance documents",
  merge_rerank: "Ranking and merging results",
  confidence_check: "Checking confidence",
  generate_answer: "Generating answer",
  citation_bind: "Binding citations",
  faithfulness_guard: "Verifying faithfulness",
  respond: "Finalizing response",
};

export function nodeLabelFor(nodeName: string): string {
  return NODE_LABELS[nodeName] ?? `Processing: ${nodeName}`;
}
