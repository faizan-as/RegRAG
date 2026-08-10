import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AnswerDisplay } from "@/components/chat/answer-display";
import { StreamProgress } from "@/components/chat/stream-progress";
import type { ChatTerminalData } from "@/hooks/use-chat-stream";

// Minimal valid terminal payload
const SESSION_ID = "sess-test";
const TURN_ID = "turn-test";

function makeTerminal(overrides: Partial<ChatTerminalData["answer"]> = {}): ChatTerminalData {
  return {
    session_id: SESSION_ID,
    turn_id: TURN_ID,
    answer: {
      text: "The regulatory guidance specifies that submissions must include a CMC section.",
      evidence: [
        {
          citation_id: "[1]",
          document_id: "doc-1",
          chunk_id: "chunk-1",
          title: "Guidance for Industry: CMC Documentation",
          section_id: "s3",
          section_title: "Section 3 — CMC",
          page_number: 5,
          passage: "Submissions must include a complete CMC section.",
          source_url: "https://www.fda.gov/guidance/cmc",
          version_hash: "abc123",
          document_status: "Final",
          retrieval_score: 0.95,
          rerank_score: 0.92,
          confidence: 0.9,
          retrieved_at: "2026-08-10T00:00:00Z",
        },
      ],
      confidence: 0.9,
      refused: false,
      refusal_reason: null,
      ...overrides,
    },
    transparency: {
      execution_trace: [],
      retrieval_diagnostics: {},
      provider_fallback_trace: [],
      ignored_filter_keys: [],
      guardrail_errors: [],
    },
  };
}

describe("AnswerDisplay – committed state", () => {
  it("renders the answer text", () => {
    render(<AnswerDisplay type="committed" terminal={makeTerminal()} />);
    expect(screen.getByTestId("answer-text")).toBeInTheDocument();
    expect(screen.getByTestId("answer-text")).toHaveTextContent(/regulatory guidance/i);
  });

  it("renders evidence citation buttons that are keyboard accessible", async () => {
    render(<AnswerDisplay type="committed" terminal={makeTerminal()} />);
    const citationBtn = screen.getByRole("button", { name: /view evidence \[1\]/i });
    expect(citationBtn).toBeInTheDocument();
    // Button should be focusable
    citationBtn.focus();
    expect(document.activeElement).toBe(citationBtn);
  });

  it("citation buttons do not appear when there is no evidence", () => {
    const terminal = makeTerminal({ evidence: [] });
    render(<AnswerDisplay type="committed" terminal={terminal} />);
    expect(screen.queryByRole("group", { name: /jump to citation/i })).not.toBeInTheDocument();
  });

  it("marks answer-display-committed testid", () => {
    render(<AnswerDisplay type="committed" terminal={makeTerminal()} />);
    expect(screen.getByTestId("answer-display-committed")).toBeInTheDocument();
  });
});

describe("AnswerDisplay – refused state (neutral, not error)", () => {
  const refusedTerminal = makeTerminal({
    refused: true,
    refusal_reason: "Insufficient grounding in retrieved evidence. Try a more specific query.",
    text: "Cannot answer.",
  });

  it("renders the refusal reason", () => {
    render(<AnswerDisplay type="refused" terminal={refusedTerminal} />);
    expect(screen.getByText(/insufficient grounding/i)).toBeInTheDocument();
  });

  it("marks answer-display-refused testid (not error testid)", () => {
    render(<AnswerDisplay type="refused" terminal={refusedTerminal} />);
    expect(screen.getByTestId("answer-display-refused")).toBeInTheDocument();
    expect(screen.queryByTestId("answer-display-committed")).not.toBeInTheDocument();
  });

  it("does not render a role=alert element (refusal is not a transport error)", () => {
    render(<AnswerDisplay type="refused" terminal={refusedTerminal} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows refinement hint", () => {
    render(<AnswerDisplay type="refused" terminal={refusedTerminal} />);
    expect(screen.getByText(/try rephrasing/i)).toBeInTheDocument();
  });
});

describe("StreamProgress – no answer text during streaming", () => {
  it("renders a polite live region", () => {
    render(<StreamProgress nodes={[]} />);
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
  });

  it("does not render answer text", () => {
    render(<StreamProgress nodes={[{ node: "generate_answer" }]} />);
    // The progress panel must never contain answer text
    expect(screen.queryByTestId("answer-text")).not.toBeInTheDocument();
    expect(screen.queryByText(/regulatory guidance specifies/i)).not.toBeInTheDocument();
  });

  it("shows human-readable node label", () => {
    render(<StreamProgress nodes={[{ node: "hybrid_retrieve" }]} latestNode={{ node: "hybrid_retrieve" }} />);
    expect(screen.getByText(/searching guidance/i)).toBeInTheDocument();
  });

  it("falls back gracefully for unknown node names", () => {
    render(<StreamProgress nodes={[]} latestNode={{ node: "unknown_future_node" }} />);
    expect(screen.getByText(/processing: unknown_future_node/i)).toBeInTheDocument();
  });
});

describe("AnswerDisplay – evidence keyboard interaction", () => {
  it("clicking a citation button does not throw and stays in document", async () => {
    const user = userEvent.setup();
    render(<AnswerDisplay type="committed" terminal={makeTerminal()} />);
    const btn = screen.getByRole("button", { name: /view evidence \[1\]/i });
    await user.click(btn);
    // After click, button should still be in the document
    expect(btn).toBeInTheDocument();
  });
});
