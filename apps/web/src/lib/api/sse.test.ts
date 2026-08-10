import { describe, expect, it } from "vitest";
import { parseChatStreamEvents } from "@/lib/api/sse";

const enc = new TextEncoder();

function makeStream(chunks: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(enc.encode(chunk));
      }
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of parseChatStreamEvents(stream)) {
    events.push(event);
  }
  return events;
}

const SESSION_ID = "sess-abc";
const TURN_ID = "turn-xyz";

const terminalPayload = {
  session_id: SESSION_ID,
  turn_id: TURN_ID,
  answer: {
    text: "Answer text from the workflow.",
    evidence: [],
    confidence: 0.9,
    refused: false,
  },
  transparency: {
    execution_trace: [],
    retrieval_diagnostics: {},
    provider_fallback_trace: [],
    ignored_filter_keys: [],
    guardrail_errors: [],
  },
};

const startedRaw = `event: started\ndata: ${JSON.stringify({ session_id: SESSION_ID })}\n\n`;
const committedRaw = `event: committed\ndata: ${JSON.stringify(terminalPayload)}\n\n`;
const doneRaw = `event: done\ndata: {}\n\n`;

describe("parseChatStreamEvents – happy path", () => {
  it("collects started, committed, done in order", async () => {
    const events = await collect(makeStream([startedRaw, committedRaw, doneRaw]));
    expect(events).toHaveLength(3);
    expect(events[0].type).toBe("started");
    expect(events[1].type).toBe("committed");
    expect(events[2].type).toBe("done");
  });

  it("parses committed payload correctly", async () => {
    const events = await collect(makeStream([startedRaw, committedRaw, doneRaw]));
    const ev = events[1];
    if (ev.type !== "committed") throw new Error("not committed");
    expect(ev.data.session_id).toBe(SESSION_ID);
    expect(ev.data.turn_id).toBe(TURN_ID);
    expect(ev.data.answer.text).toBe("Answer text from the workflow.");
  });

  it("parses refused terminal as refused type", async () => {
    const refusedPayload = {
      ...terminalPayload,
      answer: {
        text: "Cannot answer.",
        evidence: [],
        confidence: 0.1,
        refused: true,
        refusal_reason: "Insufficient grounding in retrieved evidence.",
      },
    };
    const refusedRaw = `event: refused\ndata: ${JSON.stringify(refusedPayload)}\n\n`;
    const events = await collect(makeStream([startedRaw, refusedRaw, doneRaw]));
    expect(events[1].type).toBe("refused");
    if (events[1].type === "refused") {
      expect(events[1].data.answer.refused).toBe(true);
    }
  });
});

describe("parseChatStreamEvents – split chunks", () => {
  it("reassembles events split across multiple reads", async () => {
    const full = startedRaw + committedRaw + doneRaw;
    const mid = Math.floor(full.length / 2);
    const events = await collect(makeStream([full.slice(0, mid), full.slice(mid)]));
    expect(events).toHaveLength(3);
    expect(events[1].type).toBe("committed");
  });

  it("reassembles when a single line is split across chunks", async () => {
    const eventLine = `event: started\n`;
    const dataLine = `data: ${JSON.stringify({ session_id: SESSION_ID })}\n\n`;
    const mid = Math.floor(dataLine.length / 2);
    const stream = makeStream([
      eventLine,
      dataLine.slice(0, mid),
      dataLine.slice(mid),
      committedRaw,
      doneRaw,
    ]);
    const events = await collect(stream);
    expect(events[0].type).toBe("started");
    expect(events[1].type).toBe("committed");
  });
});

describe("parseChatStreamEvents – CRLF / multiline", () => {
  it("handles CRLF line endings", async () => {
    const toCRLF = (s: string) => s.replace(/\n/g, "\r\n");
    const stream = makeStream([toCRLF(startedRaw), toCRLF(committedRaw), toCRLF(doneRaw)]);
    const events = await collect(stream);
    expect(events[0].type).toBe("started");
    expect(events[1].type).toBe("committed");
  });

  it("joins multiple data: lines with a newline before parsing", async () => {
    // JSON is valid when split across two data: lines because whitespace is allowed
    const part1 = '{"node":';
    const part2 = '"query_understand"}';
    const multiLineNode = `event: node\ndata: ${part1}\ndata: ${part2}\n\n`;
    const stream = makeStream([startedRaw, multiLineNode, committedRaw, doneRaw]);
    const events = await collect(stream);
    expect(events[1].type).toBe("node");
    if (events[1].type === "node") {
      expect(events[1].data.node).toBe("query_understand");
    }
  });
});

describe("parseChatStreamEvents – comments", () => {
  it("ignores SSE comment lines (: prefix)", async () => {
    const withComments =
      `: heartbeat\n${startedRaw}: another comment\n${committedRaw}${doneRaw}`;
    const events = await collect(makeStream([withComments]));
    expect(events[0].type).toBe("started");
    expect(events[1].type).toBe("committed");
    expect(events[2].type).toBe("done");
  });
});

describe("parseChatStreamEvents – wrapper normalization", () => {
  it("unwraps envelope {event, data} from data field when event name matches", async () => {
    // Backend may emit: event: committed\ndata: {"event":"committed","data":{...terminal}}\n\n
    const wrapped = { event: "committed", data: terminalPayload };
    const wrappedRaw = `event: committed\ndata: ${JSON.stringify(wrapped)}\n\n`;
    const events = await collect(makeStream([startedRaw, wrappedRaw, doneRaw]));
    expect(events[1].type).toBe("committed");
    if (events[1].type === "committed") {
      expect(events[1].data.session_id).toBe(SESSION_ID);
    }
  });

  it("accepts direct terminal payload without wrapper", async () => {
    // event: committed\ndata: {session_id, turn_id, answer, transparency}\n\n
    const events = await collect(makeStream([startedRaw, committedRaw, doneRaw]));
    expect(events[1].type).toBe("committed");
    if (events[1].type === "committed") {
      expect(events[1].data.session_id).toBe(SESSION_ID);
    }
  });

  it("uses event name from wrapper if frame event field matches", async () => {
    const wrappedStarted = {
      event: "started",
      data: { session_id: SESSION_ID },
    };
    const wRaw = `event: started\ndata: ${JSON.stringify(wrappedStarted)}\n\n`;
    const events = await collect(makeStream([wRaw, committedRaw, doneRaw]));
    expect(events[0].type).toBe("started");
  });
});

describe("parseChatStreamEvents – malformed JSON", () => {
  it("throws on invalid JSON in data field", async () => {
    const badJson = `event: committed\ndata: {not: valid json\n\n`;
    await expect(collect(makeStream([startedRaw, badJson]))).rejects.toThrow(
      /malformed sse json/i,
    );
  });

  it("throws when committed payload is missing required fields", async () => {
    const incomplete = { session_id: SESSION_ID }; // missing turn_id, answer, transparency
    const incompleteRaw = `event: committed\ndata: ${JSON.stringify(incomplete)}\n\n`;
    await expect(collect(makeStream([startedRaw, incompleteRaw]))).rejects.toThrow(
      /invalid committed payload/i,
    );
  });
});

describe("parseChatStreamEvents – terminal ordering / duplicate rejection", () => {
  it("throws when a second terminal event appears", async () => {
    const stream = makeStream([startedRaw, committedRaw, committedRaw, doneRaw]);
    await expect(collect(stream)).rejects.toThrow(/multiple terminal/i);
  });

  it("throws when stream closes without any terminal event", async () => {
    await expect(collect(makeStream([startedRaw]))).rejects.toThrow(
      /without committed or refused/i,
    );
  });
});

describe("parseChatStreamEvents – node event safety", () => {
  it("rejects node events that contain answer text (answer key)", async () => {
    const badNode = { node: "generate_answer", answer: { text: "leaked answer text" } };
    const badNodeRaw = `event: node\ndata: ${JSON.stringify(badNode)}\n\n`;
    await expect(collect(makeStream([startedRaw, badNodeRaw]))).rejects.toThrow(
      /node payload/i,
    );
  });

  it("rejects node events that contain a top-level text key", async () => {
    const badNode = { node: "generate_answer", text: "leaked text" };
    const badNodeRaw = `event: node\ndata: ${JSON.stringify(badNode)}\n\n`;
    await expect(collect(makeStream([startedRaw, badNodeRaw]))).rejects.toThrow(
      /node payload/i,
    );
  });

  it("accepts node events with safe metadata only", async () => {
    const safeNode = {
      node: "merge_rerank",
      evidence_count: 5,
      confidence: 0.8,
      status: "completed",
    };
    const safeNodeRaw = `event: node\ndata: ${JSON.stringify(safeNode)}\n\n`;
    const events = await collect(makeStream([startedRaw, safeNodeRaw, committedRaw, doneRaw]));
    expect(events[1].type).toBe("node");
    if (events[1].type === "node") {
      expect(events[1].data.node).toBe("merge_rerank");
    }
  });
});
