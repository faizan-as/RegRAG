import type { components } from "@/lib/api/schema";

export type ApiErrorCategory =
  | "unauthenticated"
  | "unauthorized"
  | "validation"
  | "not_found"
  | "rate_limited"
  | "unavailable"
  | "unknown";

type ErrorEnvelope = components["schemas"]["ErrorResponse"];

export type RetryAfterInfo = {
  raw: string;
  seconds?: number;
  retryAt?: Date;
};

export type ApiClientErrorInit = {
  category: ApiErrorCategory;
  message: string;
  status: number;
  requestId?: string;
  details?: Array<Record<string, unknown>>;
  retryAfter?: RetryAfterInfo;
  isCanceled?: boolean;
};

export class ApiClientError extends Error {
  category: ApiErrorCategory;
  status: number;
  requestId?: string;
  details?: Array<Record<string, unknown>>;
  retryAfter?: RetryAfterInfo;
  isCanceled: boolean;

  constructor(init: ApiClientErrorInit) {
    super(init.message);
    this.name = "ApiClientError";
    this.category = init.category;
    this.status = init.status;
    this.requestId = init.requestId;
    this.details = init.details;
    this.retryAfter = init.retryAfter;
    this.isCanceled = Boolean(init.isCanceled);
  }
}

export function isApiClientError(error: unknown): error is ApiClientError {
  return error instanceof ApiClientError;
}

export function parseRetryAfter(retryAfterValue: string | null): RetryAfterInfo | undefined {
  if (!retryAfterValue) {
    return undefined;
  }

  const trimmed = retryAfterValue.trim();
  if (!trimmed) {
    return undefined;
  }

  const asSeconds = Number(trimmed);
  if (Number.isFinite(asSeconds) && asSeconds >= 0) {
    return {
      raw: trimmed,
      seconds: Math.floor(asSeconds),
    };
  }

  const asDate = new Date(trimmed);
  if (!Number.isNaN(asDate.getTime())) {
    const deltaMs = Math.max(asDate.getTime() - Date.now(), 0);
    return {
      raw: trimmed,
      retryAt: asDate,
      seconds: Math.ceil(deltaMs / 1000),
    };
  }

  return {
    raw: trimmed,
  };
}

function categoryFromStatus(status: number): ApiErrorCategory {
  if (status === 401) {
    return "unauthenticated";
  }
  if (status === 403) {
    return "unauthorized";
  }
  if (status === 422) {
    return "validation";
  }
  if (status === 404) {
    return "not_found";
  }
  if (status === 429) {
    return "rate_limited";
  }
  if (status === 503) {
    return "unavailable";
  }
  return "unknown";
}

function coerceErrorEnvelope(payload: unknown): ErrorEnvelope | undefined {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }

  const maybeError = (payload as { error?: unknown }).error;
  if (!maybeError || typeof maybeError !== "object") {
    return undefined;
  }

  const message = (maybeError as { message?: unknown }).message;
  const category = (maybeError as { category?: unknown }).category;
  if (typeof message !== "string" || typeof category !== "string") {
    return undefined;
  }

  return payload as ErrorEnvelope;
}

export function normalizeApiError(args: {
  status: number;
  statusText: string;
  headers: Headers;
  payload?: unknown;
}): ApiClientError {
  const envelope = coerceErrorEnvelope(args.payload);
  const fallbackMessage = args.statusText || "Request failed";
  const requestIdFromHeader = args.headers.get("x-request-id") ?? undefined;
  const retryAfter = parseRetryAfter(args.headers.get("retry-after"));

  return new ApiClientError({
    category: categoryFromStatus(args.status),
    status: args.status,
    message: envelope?.error.message || fallbackMessage,
    requestId: envelope?.error.request_id ?? requestIdFromHeader,
    details: (envelope?.error.details as Array<Record<string, unknown>> | undefined) ?? undefined,
    retryAfter,
  });
}

export function createCanceledError(): ApiClientError {
  return new ApiClientError({
    category: "unknown",
    status: 0,
    message: "Request canceled.",
    isCanceled: true,
  });
}

export function describeApiError(
  error: ApiClientError,
  context: Partial<{
    unauthenticated: string;
    unauthorized: string;
    notFound: string;
    validation: string;
    rateLimited: string;
    unavailable: string;
    unknown: string;
  }> = {},
): string {
  switch (error.category) {
    case "unauthenticated":
      return context.unauthenticated ?? "Sign in again to continue.";
    case "unauthorized":
      return context.unauthorized ?? "You do not have access to this record.";
    case "not_found":
      return context.notFound ?? "The requested record is not available.";
    case "validation":
      return context.validation ?? "Review the request and try again.";
    case "rate_limited": {
      if (error.retryAfter?.seconds) {
        return context.rateLimited ?? `Try again in about ${error.retryAfter.seconds} seconds.`;
      }
      return context.rateLimited ?? "Try again after the service interval resets.";
    }
    case "unavailable":
      return context.unavailable ?? "The service is temporarily unavailable. Try again shortly.";
    default:
      return context.unknown ?? error.message;
  }
}
