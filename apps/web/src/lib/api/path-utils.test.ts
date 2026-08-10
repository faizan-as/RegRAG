import { describe, expect, it } from "vitest";
import { buildPath, encodePathSegment } from "@/lib/api/client";

describe("encodePathSegment", () => {
  it("encodes path separators and spaces", () => {
    expect(encodePathSegment("doc id/with space")).toBe("doc%20id%2Fwith%20space");
  });
});

describe("buildPath", () => {
  it("replaces path template variables with encoded values", () => {
    const result = buildPath("/api/documents/{document_id}/passages/{chunk_id}", {
      document_id: "doc/alpha",
      chunk_id: "chunk 1",
    });

    expect(result).toBe("/api/documents/doc%2Falpha/passages/chunk%201");
  });

  it("throws when required path values are missing", () => {
    expect(() =>
      buildPath("/api/documents/{document_id}", {
        other: "value",
      } as unknown as Record<string, string>),
    ).toThrow("Missing path parameter: document_id");
  });
});