import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuditWorkspace } from "@/components/admin/audit-workspace";

const getAudit = vi.fn();
const searchParams = new URLSearchParams();

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({
    getAudit,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/admin/audit",
  useSearchParams: () => searchParams,
}));

beforeEach(() => {
  vi.clearAllMocks();
  getAudit.mockResolvedValue({ events: [], limit: 20, offset: 0 });
});

afterEach(() => {
  cleanup();
});

function renderAudit() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuditWorkspace />
    </QueryClientProvider>,
  );
}

describe("AuditWorkspace", () => {
  it("renders payload text without executing markup", async () => {
    getAudit.mockResolvedValue({
      events: [
        {
          event_id: "event-1",
          event_type: "alert.updated",
          user_id: "user-1",
          session_id: "session-1",
          route: "/admin/audit",
          request_id: "req-1",
          payload: { script: "<script>window.__AUDIT_TEST__ = true</script>", nested: { ok: true } },
          created_at: "2026-08-10T12:00:00Z",
        },
      ],
      limit: 20,
      offset: 0,
    });

    renderAudit();

    await userEvent.click((await screen.findAllByRole("button", { name: /view payload/i }))[0]);

    expect(screen.getByText(/<script>window.__AUDIT_TEST__ = true<\/script>/i)).toBeInTheDocument();
    expect((globalThis as { __AUDIT_TEST__?: boolean }).__AUDIT_TEST__).toBeUndefined();
  });

  it("does not render total pagination counts", async () => {
    getAudit.mockResolvedValue({
      events: [],
      limit: 20,
      offset: 0,
    });

    renderAudit();

    expect(await screen.findByText(/no audit events match/i)).toBeInTheDocument();
    expect(screen.queryByText(/of\s+\d+/i)).not.toBeInTheDocument();
  });
});