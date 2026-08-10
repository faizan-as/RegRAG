import type { components } from "@/lib/api/schema";
import { createCanceledError } from "@/lib/api/errors";

export type AnswerModel = components["schemas"]["Answer"];
export type TransparencyMetadataModel = components["schemas"]["TransparencyMetadata"];

type ChatStreamEnvelope = {
  event: string;
  data?: unknown;
};

export type ChatStartedData = {
  session_id: string;
};

export type ChatNodeData = {
  node: string;
  started_at?: string | null;
  completed_at?: string | null;
  status?: string | null;
  provider?: string | null;
  evidence_count?: number | null;
  confidence?: number | null;
  retry_count?: number | null;
  diagnostics?: Record<string, unknown> | null;
};

export type ChatTerminalData = {
  session_id: string;
  turn_id: string;
  answer: AnswerModel;
  transparency: TransparencyMetadataModel;
};

export type ChatErrorData = {
  message: string;
};

export type ParsedChatStreamEvent =
  | { type: "started"; data: ChatStartedData }
  | { type: "node"; data: ChatNodeData }
  | { type: "committed"; data: ChatTerminalData }
  | { type: "refused"; data: ChatTerminalData }
  | { type: "error"; data: ChatErrorData }
  | { type: "done" };

type RawSseFrame = {
  event: string;
  data: string;
};

type FrameAccumulator = {
  event?: string;
  dataLines: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasString(value: unknown, key: string): value is Record<string, string> {
  return isRecord(value) && typeof value[key] === "string";
}

export function isChatStartedData(value: unknown): value is ChatStartedData {
  return hasString(value, "session_id");
}

export function isChatNodeData(value: unknown): value is ChatNodeData {
  if (!hasString(value, "node")) {
    return false;
  }

  if ("answer" in value || "text" in value) {
    return false;
  }

  return true;
}

export function isChatTerminalData(value: unknown): value is ChatTerminalData {
  if (!hasString(value, "session_id") || !hasString(value, "turn_id") || !isRecord(value.answer)) {
    return false;
  }

  if (typeof value.answer.text !== "string" || !Array.isArray(value.answer.evidence)) {
    return false;
  }

  return isRecord(value.transparency);
}

export function isChatErrorData(value: unknown): value is ChatErrorData {
  return hasString(value, "message");
}

function isChatStreamEnvelope(value: unknown): value is ChatStreamEnvelope {
  return hasString(value, "event");
}

function assertNotAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw createCanceledError();
  }
}

function parseFrameJson(frame: RawSseFrame): unknown {
  if (!frame.data.trim()) {
    return undefined;
  }

  try {
    return JSON.parse(frame.data);
  } catch {
    throw new Error(`Malformed SSE JSON for event '${frame.event}'.`);
  }
}

function normalizeChatEvent(frame: RawSseFrame): ParsedChatStreamEvent {
  const parsed = parseFrameJson(frame);
  const wrapped = isChatStreamEnvelope(parsed) ? parsed : undefined;
  const eventName = (wrapped?.event ?? frame.event).toLowerCase();
  const eventPayload = wrapped && "data" in wrapped ? wrapped.data : parsed;

  if (eventName === "started") {
    if (!isChatStartedData(eventPayload)) {
      throw new Error("Invalid started payload in SSE stream.");
    }
    return { type: "started", data: eventPayload };
  }

  if (eventName === "node") {
    if (!isChatNodeData(eventPayload)) {
      throw new Error("Invalid node payload in SSE stream.");
    }
    return { type: "node", data: eventPayload };
  }

  if (eventName === "committed" || eventName === "refused") {
    if (!isChatTerminalData(eventPayload)) {
      throw new Error(`Invalid ${eventName} payload in SSE stream.`);
    }
    return {
      type: eventName,
      data: eventPayload,
    };
  }

  if (eventName === "error") {
    if (!isChatErrorData(eventPayload)) {
      throw new Error("Invalid error payload in SSE stream.");
    }
    return { type: "error", data: eventPayload };
  }

  if (eventName === "done") {
    return { type: "done" };
  }

  throw new Error(`Unsupported SSE event '${eventName}'.`);
}

function frameHasContent(frame: FrameAccumulator): boolean {
  return Boolean(frame.event) || frame.dataLines.length > 0;
}

function finalizeFrame(frame: FrameAccumulator): RawSseFrame | null {
  if (!frameHasContent(frame)) {
    return null;
  }

  const next: RawSseFrame = {
    event: frame.event ?? "message",
    data: frame.dataLines.join("\n"),
  };

  frame.event = undefined;
  frame.dataLines = [];
  return next;
}

function consumeSseLine(line: string, frame: FrameAccumulator): RawSseFrame | null {
  if (!line) {
    return finalizeFrame(frame);
  }

  if (line.startsWith(":")) {
    return null;
  }

  const separator = line.indexOf(":");
  const field = separator >= 0 ? line.slice(0, separator) : line;
  const rawValue = separator >= 0 ? line.slice(separator + 1) : "";
  const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;

  if (field === "event") {
    frame.event = value;
    return null;
  }

  if (field === "data") {
    frame.dataLines.push(value);
    return null;
  }

  return null;
}

async function* parseSseFrames(
  stream: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<RawSseFrame> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const frame: FrameAccumulator = { dataLines: [] };
  let buffer = "";

  try {
    while (true) {
      assertNotAborted(signal);
      const chunk = await reader.read();
      if (chunk.done) {
        break;
      }

      buffer += decoder.decode(chunk.value, { stream: true });

      while (true) {
        const lfIndex = buffer.indexOf("\n");
        const crIndex = buffer.indexOf("\r");
        const breakIndex =
          lfIndex === -1
            ? crIndex
            : crIndex === -1
              ? lfIndex
              : Math.min(lfIndex, crIndex);

        if (breakIndex === -1) {
          break;
        }

        const line = buffer.slice(0, breakIndex);
        const delimiterSize =
          buffer[breakIndex] === "\r" && buffer[breakIndex + 1] === "\n" ? 2 : 1;
        buffer = buffer.slice(breakIndex + delimiterSize);

        const maybeFrame = consumeSseLine(line, frame);
        if (maybeFrame) {
          yield maybeFrame;
        }
      }
    }

    buffer += decoder.decode();
    if (buffer.length > 0) {
      const maybeFrame = consumeSseLine(buffer, frame);
      if (maybeFrame) {
        yield maybeFrame;
      }
    }

    const trailing = finalizeFrame(frame);
    if (trailing) {
      yield trailing;
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw createCanceledError();
    }
    throw error;
  } finally {
    reader.releaseLock();
  }
}

export async function* parseChatStreamEvents(
  stream: ReadableStream<Uint8Array>,
  options: { signal?: AbortSignal } = {},
): AsyncGenerator<ParsedChatStreamEvent> {
  let terminalSeen = false;
  let doneSeen = false;

  for await (const frame of parseSseFrames(stream, options.signal)) {
    const event = normalizeChatEvent(frame);

    if (doneSeen) {
      throw new Error("SSE stream emitted events after done.");
    }

    if (event.type === "committed" || event.type === "refused") {
      if (terminalSeen) {
        throw new Error("SSE stream emitted multiple terminal events.");
      }
      terminalSeen = true;
      yield event;
      continue;
    }

    if (event.type === "done") {
      doneSeen = true;
      if (!terminalSeen) {
        throw new Error("SSE stream ended without committed or refused terminal payload.");
      }
      yield event;
      continue;
    }

    yield event;
  }

  if (!terminalSeen) {
    throw new Error("SSE stream closed without committed or refused terminal payload.");
  }
}
