"use client";

import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { getRequiredPublicEnv } from "@/lib/env";
import type { components } from "@/lib/api/schema";
import { ApiClientError, createCanceledError, normalizeApiError } from "@/lib/api/errors";
import { parseChatStreamEvents, type ParsedChatStreamEvent } from "@/lib/api/sse";

type SearchRequest = components["schemas"]["SearchRequest"];
type SearchResponse = components["schemas"]["SearchResponse"];
type AnswerRequest = components["schemas"]["AnswerRequest"];
type AlertListResponse = components["schemas"]["AlertListResponse"];
type AlertResponse = components["schemas"]["AlertResponse"];
type AlertStatus = components["schemas"]["AlertStatus"];
type AlertUpdateRequest = components["schemas"]["AlertUpdateRequest"];
type AuditListResponse = components["schemas"]["AuditListResponse"];
type SessionCreateRequest = components["schemas"]["SessionCreateRequest"];
type SessionResponse = components["schemas"]["SessionResponse"];
type SessionListResponse = components["schemas"]["SessionListResponse"];
type SessionHistoryResponse = components["schemas"]["SessionHistoryResponse"];
type SummaryRequest = components["schemas"]["SummaryRequest"];
type SummaryResult = components["schemas"]["SummaryResult"];
type ExportRequest = components["schemas"]["ExportRequest"];
type ExportResult = components["schemas"]["ExportResult"];
type GuidanceDocument = components["schemas"]["GuidanceDocument"];
type SectionNavigationEntry = components["schemas"]["SectionNavigationEntry"];
type PassageResponse = components["schemas"]["PassageResponse"];

export type AuditQueryFilters = {
  event_type?: string;
  user_id?: string;
  session_id?: string;
  route?: string;
  created_from?: string;
  created_to?: string;
};

type QueryValue = string | number | boolean | Array<string | number | boolean> | null | undefined;
type RequestMethod = "GET" | "POST" | "PATCH";

type RequestOptions = {
  signal?: AbortSignal;
  query?: Record<string, QueryValue>;
  parseAs?: "json" | "blob";
};

export function encodePathSegment(value: string | number): string {
  return encodeURIComponent(String(value));
}

export function buildPath(
  template: string,
  pathParams: Record<string, string | number>,
): string {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key: string) => {
    const value = pathParams[key];
    if (value === undefined || value === null) {
      throw new Error(`Missing path parameter: ${key}`);
    }
    return encodePathSegment(value);
  });
}

function appendQuery(url: URL, query: Record<string, QueryValue> | undefined): void {
  if (!query) {
    return;
  }

  for (const [key, rawValue] of Object.entries(query)) {
    if (rawValue === undefined || rawValue === null || rawValue === "") {
      continue;
    }
    if (Array.isArray(rawValue)) {
      for (const entry of rawValue) {
        if (entry !== undefined && entry !== null && String(entry) !== "") {
          url.searchParams.append(key, String(entry));
        }
      }
      continue;
    }
    url.searchParams.append(key, String(rawValue));
  }
}

async function parseJsonSafely(response: Response): Promise<unknown | undefined> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return undefined;
  }

  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

async function getAccessToken(): Promise<string | null> {
  const supabase = createSupabaseBrowserClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

async function refreshAccessToken(): Promise<string | null> {
  const supabase = createSupabaseBrowserClient();
  const { data } = await supabase.auth.refreshSession();
  return data.session?.access_token ?? null;
}

function mergeAbortSignals(...signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const activeSignals = signals.filter((value): value is AbortSignal => Boolean(value));
  if (activeSignals.length === 0) {
    return undefined;
  }

  if (activeSignals.length === 1) {
    return activeSignals[0];
  }

  const controller = new AbortController();
  const abort = () => {
    controller.abort();
  };

  for (const signal of activeSignals) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", abort, { once: true });
  }

  return controller.signal;
}

export type ChatStreamHandle = {
  controller: AbortController;
  events: AsyncGenerator<ParsedChatStreamEvent>;
};

export class ApiClient {
  private readonly baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  async search(request: SearchRequest, options: RequestOptions = {}): Promise<SearchResponse> {
    return this.requestJson<SearchResponse>("POST", "/api/search", {
      body: request,
      signal: options.signal,
    });
  }

  async createSummary(request: SummaryRequest, options: RequestOptions = {}): Promise<SummaryResult> {
    return this.requestJson<SummaryResult>("POST", "/api/summaries", {
      body: request,
      signal: options.signal,
    });
  }

  async getSummary(summaryId: string, options: RequestOptions = {}): Promise<SummaryResult> {
    const path = buildPath("/api/summaries/{summary_id}", {
      summary_id: summaryId,
    });
    return this.requestJson<SummaryResult>("GET", path, {
      signal: options.signal,
    });
  }

  async listSessions(
    args: { limit?: number; offset?: number } = {},
    options: RequestOptions = {},
  ): Promise<SessionListResponse> {
    return this.requestJson<SessionListResponse>("GET", "/api/sessions", {
      signal: options.signal,
      query: {
        limit: args.limit,
        offset: args.offset,
      },
    });
  }

  async createSession(
    request: SessionCreateRequest = {},
    options: RequestOptions = {},
  ): Promise<SessionResponse> {
    return this.requestJson<SessionResponse>("POST", "/api/sessions", {
      body: request,
      signal: options.signal,
    });
  }

  async listSessionTurns(
    sessionId: string,
    options: RequestOptions = {},
  ): Promise<SessionHistoryResponse> {
    const path = buildPath("/api/sessions/{session_id}/turns", {
      session_id: sessionId,
    });
    return this.requestJson<SessionHistoryResponse>("GET", path, {
      signal: options.signal,
    });
  }

  async createExport(request: ExportRequest, options: RequestOptions = {}): Promise<ExportResult> {
    return this.requestJson<ExportResult>("POST", "/api/exports", {
      body: request,
      signal: options.signal,
    });
  }

  async getAlerts(
    status?: AlertStatus,
    limit?: number,
    offset?: number,
    options: RequestOptions = {},
  ): Promise<AlertListResponse> {
    return this.requestJson<AlertListResponse>("GET", "/api/alerts", {
      signal: options.signal,
      query: { status, limit, offset },
    });
  }

  async patchAlert(
    alertId: string,
    status: AlertStatus,
    options: RequestOptions = {},
  ): Promise<AlertResponse> {
    const path = buildPath("/api/alerts/{alert_id}", { alert_id: alertId });
    const body: AlertUpdateRequest = { status };
    return this.requestJson<AlertResponse>("PATCH", path, {
      body,
      signal: options.signal,
    });
  }

  async getAudit(
    filters: AuditQueryFilters = {},
    limit?: number,
    offset?: number,
    options: RequestOptions = {},
  ): Promise<AuditListResponse> {
    return this.requestJson<AuditListResponse>("GET", "/api/audit", {
      signal: options.signal,
      query: { ...filters, limit, offset },
    });
  }

  async getDocument(documentId: string, options: RequestOptions = {}): Promise<GuidanceDocument> {
    const path = buildPath("/api/documents/{document_id}", {
      document_id: documentId,
    });
    return this.requestJson<GuidanceDocument>("GET", path, {
      signal: options.signal,
    });
  }

  async getSections(
    documentId: string,
    options: RequestOptions = {},
  ): Promise<SectionNavigationEntry[]> {
    const path = buildPath("/api/documents/{document_id}/sections", {
      document_id: documentId,
    });
    return this.requestJson<SectionNavigationEntry[]>("GET", path, {
      signal: options.signal,
    });
  }

  async getPassage(
    documentId: string,
    chunkId: string,
    options: RequestOptions = {},
  ): Promise<PassageResponse> {
    const path = buildPath("/api/documents/{document_id}/passages/{chunk_id}", {
      document_id: documentId,
      chunk_id: chunkId,
    });
    return this.requestJson<PassageResponse>("GET", path, {
      signal: options.signal,
    });
  }

  async getExport(exportId: string, options: RequestOptions = {}): Promise<ExportResult> {
    const path = buildPath("/api/exports/{export_id}", {
      export_id: exportId,
    });
    return this.requestJson<ExportResult>("GET", path, {
      signal: options.signal,
    });
  }

  async downloadExport(exportId: string, options: RequestOptions = {}): Promise<Response> {
    const path = buildPath("/api/exports/{export_id}/download", {
      export_id: exportId,
    });
    return this.requestRaw("GET", path, {
      signal: options.signal,
      parseAs: "blob",
    });
  }

  async openChatStream(
    request: AnswerRequest,
    options: { signal?: AbortSignal } = {},
  ): Promise<ChatStreamHandle> {
    const controller = new AbortController();
    const signal = mergeAbortSignals(options.signal, controller.signal);
    const response = await this.requestRaw("POST", "/api/chat/stream", {
      body: request,
      signal,
      parseAs: "json",
    });

    const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
    if (!contentType.includes("text/event-stream")) {
      throw new ApiClientError({
        category: "unknown",
        status: response.status,
        message: "Expected text/event-stream response from chat stream endpoint.",
      });
    }

    if (!response.body) {
      throw new ApiClientError({
        category: "unavailable",
        status: 503,
        message: "Chat stream body is unavailable.",
      });
    }

    return {
      controller,
      events: parseChatStreamEvents(response.body, { signal }),
    };
  }

  async getArtifactBlob(
    documentId: string,
    artifactId: string,
    options: RequestOptions = {},
  ): Promise<Response> {
    const path = buildPath("/api/documents/{document_id}/artifacts/{artifact_id}/download", {
      document_id: documentId,
      artifact_id: artifactId,
    });
    return this.requestRaw("GET", path, { signal: options.signal, parseAs: "blob" });
  }

  async downloadArtifact(
    documentId: string,
    artifactId: string,
    options: RequestOptions = {},
  ): Promise<Response> {
    return this.getArtifactBlob(documentId, artifactId, options);
  }

  private async requestJson<T>(
    method: RequestMethod,
    path: string,
    args: {
      body?: unknown;
      signal?: AbortSignal;
      query?: Record<string, QueryValue>;
    },
  ): Promise<T> {
    const response = await this.requestRaw(method, path, {
      signal: args.signal,
      query: args.query,
      body: args.body,
      parseAs: "json",
    });

    const parsed = await parseJsonSafely(response);
    return (parsed ?? {}) as T;
  }

  private async requestRaw(
    method: RequestMethod,
    path: string,
    args: {
      body?: unknown;
      signal?: AbortSignal;
      query?: Record<string, QueryValue>;
      parseAs: "json" | "blob";
    },
  ): Promise<Response> {
    const execute = async (accessToken: string | null): Promise<Response> => {
      if (!accessToken) {
        throw new ApiClientError({
          category: "unauthenticated",
          status: 401,
          message: "Sign in required.",
        });
      }

      const url = new URL(path, this.baseUrl);
      appendQuery(url, args.query);

      const headers: HeadersInit = {
        authorization: `Bearer ${accessToken}`,
      };
      if (args.body !== undefined) {
        headers["content-type"] = "application/json";
      }

      return fetch(url.toString(), {
        method,
        signal: args.signal,
        headers,
        body: args.body !== undefined ? JSON.stringify(args.body) : undefined,
      });
    };

    let response: Response;
    try {
      const initialToken = await getAccessToken();
      response = await execute(initialToken);
      if (response.status === 401) {
        const refreshedToken = await refreshAccessToken();
        response = await execute(refreshedToken);
      }
    } catch (error) {
      if (error instanceof ApiClientError) {
        throw error;
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw createCanceledError();
      }
      throw new ApiClientError({
        category: "unavailable",
        status: 503,
        message: "Service is temporarily unavailable.",
      });
    }

    if (!response.ok) {
      const payload = await parseJsonSafely(response);
      throw normalizeApiError({
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
        payload,
      });
    }

    return response;
  }
}

let defaultClient: ApiClient | null = null;

export function createApiClient(): ApiClient {
  if (defaultClient) {
    return defaultClient;
  }

  const env = getRequiredPublicEnv();
  defaultClient = new ApiClient(env.NEXT_PUBLIC_API_BASE_URL);
  return defaultClient;
}
