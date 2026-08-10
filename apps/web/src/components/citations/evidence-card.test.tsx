import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it } from "vitest";
import { EvidenceCard } from "@/components/citations/evidence-card";

type Evidence = ComponentProps<typeof EvidenceCard>["evidence"];

const evidence = {
  citation_id: "[1]",
  document_id: "example-guidance",
  chunk_id: "example-guidance:version:1",
  title: "Example FDA Guidance",
  section_id: "recommendations",
  section_title: "Recommendations",
  page_number: 4,
  passage: "FDA recommends a supported labeling statement.",
  source_url: "https://www.fda.gov/example-guidance",
  document_status: "Final",
  version_hash: "a".repeat(64),
  retrieval_score: 0.5,
  rerank_score: 0.8,
  confidence: 0.7,
  retrieved_at: "2026-08-10T08:00:00Z",
} satisfies Evidence;

describe("EvidenceCard", () => {
  it("renders source actions as links rather than button primitives", () => {
    render(<EvidenceCard evidence={evidence} />);

    const passageLink = screen.getByRole("link", { name: "Open source passage" });
    const fdaLink = screen.getByRole("link", { name: "FDA source" });

    expect(passageLink.tagName).toBe("A");
    expect(passageLink).toHaveAttribute(
      "href",
      expect.stringContaining("/documents/example-guidance?chunk=example-guidance%3Aversion%3A1"),
    );
    expect(fdaLink).toHaveAttribute("href", evidence.source_url);
  });
});