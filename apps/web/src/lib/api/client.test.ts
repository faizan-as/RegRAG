import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api/client";

const getSession = vi.fn();
const refreshSession = vi.fn();

vi.mock("@/lib/supabase/browser", () => ({
  createSupabaseBrowserClient: () => ({
    auth: {
      getSession,
      refreshSession,
    },
  }),
}));

describe("ApiClient alerts and audit queries", () => {
  beforeEach(() => {
    getSession.mockResolvedValue({ data: { session: { access_token: "token-123" } } });
    refreshSession.mockResolvedValue({ data: { session: { access_token: "token-123" } } });
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ alerts: [], limit: 10, offset: 0, events: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;
  });

  it("builds alert and audit query strings safely", async () => {
    const client = new ApiClient("https://example.test");

    await client.getAlerts("open", 12, 24);
    await client.patchAlert("alert/one", "acknowledged");
    await client.getAudit(
      {
        event_type: "alert.updated",
        user_id: "user 1",
        session_id: "session/2",
        route: "/admin/audit?x=1",
        created_from: "2026-08-01",
        created_to: "2026-08-10",
      },
      25,
      50,
    );

    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      "https://example.test/api/alerts?status=open&limit=12&offset=24",
      expect.objectContaining({ method: "GET" }),
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      "https://example.test/api/alerts/alert%2Fone",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "acknowledged" }) }),
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      3,
      "https://example.test/api/audit?event_type=alert.updated&user_id=user+1&session_id=session%2F2&route=%2Fadmin%2Faudit%3Fx%3D1&created_from=2026-08-01&created_to=2026-08-10&limit=25&offset=50",
      expect.objectContaining({ method: "GET" }),
    );
  });
});
