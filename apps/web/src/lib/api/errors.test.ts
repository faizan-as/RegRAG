import { describe, expect, it } from "vitest";
import { normalizeApiError, parseRetryAfter } from "@/lib/api/errors";

describe("parseRetryAfter", () => {
  it("parses retry-after seconds", () => {
    const parsed = parseRetryAfter("120");
    expect(parsed?.seconds).toBe(120);
    expect(parsed?.retryAt).toBeUndefined();
  });

  it("parses retry-after date", () => {
    const parsed = parseRetryAfter("Wed, 21 Oct 2030 07:28:00 GMT");
    expect(parsed?.retryAt).toBeInstanceOf(Date);
    expect(parsed?.seconds).toBeGreaterThanOrEqual(0);
  });
});

describe("normalizeApiError", () => {
  it("maps known status categories and preserves request id", () => {
    const headers = new Headers({ "x-request-id": "req-header" });
    const error = normalizeApiError({
      status: 422,
      statusText: "Unprocessable Entity",
      headers,
      payload: {
        error: {
          category: "validation",
          message: "Validation failed",
          request_id: "req-body",
          details: [{ field: "query" }],
        },
      },
    });

    expect(error.category).toBe("validation");
    expect(error.status).toBe(422);
    expect(error.requestId).toBe("req-body");
    expect(error.details).toEqual([{ field: "query" }]);
  });

  it("falls back to header request id and unknown category", () => {
    const error = normalizeApiError({
      status: 500,
      statusText: "Internal Server Error",
      headers: new Headers({ "x-request-id": "req-fallback" }),
      payload: undefined,
    });

    expect(error.category).toBe("unknown");
    expect(error.requestId).toBe("req-fallback");
    expect(error.message).toBe("Internal Server Error");
  });
});
