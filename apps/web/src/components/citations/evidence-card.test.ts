import { describe, expect, it } from "vitest";
import { buildEvidenceDocumentHref } from "@/components/citations/evidence-card";

describe("buildEvidenceDocumentHref", () => {
  it("encodes document/chunk identifiers and includes page/version params", () => {
    const href = buildEvidenceDocumentHref({
      citation_id: "[1]",
      document_id: "doc/alpha",
      chunk_id: "chunk 1",
      title: "Guidance",
      section_id: "s1",
      section_title: "Section 1",
      page_number: 8,
      passage: "text",
      source_url: "https://example.com",
      version_hash: "abc123",
      document_status: "Final",
      retrieval_score: 0.9,
      rerank_score: 0.8,
      confidence: 0.7,
      retrieved_at: "2026-08-07T00:00:00Z",
    });

    expect(href).toBe("/documents/doc%2Falpha?chunk=chunk+1&section=s1&page=8&version=abc123");
  });
});
