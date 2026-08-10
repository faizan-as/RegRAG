import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DisplayRoleProvider } from "@/components/app-shell/display-role-context";
import { AlertsWorkspace } from "@/components/alerts/alerts-workspace";
import { ApiClientError } from "@/lib/api/errors";

const getAlerts = vi.fn();
const patchAlert = vi.fn();
const searchParams = new URLSearchParams();

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({
    getAlerts,
    patchAlert,
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/alerts",
  useSearchParams: () => searchParams,
}));

beforeEach(() => {
  vi.clearAllMocks();
  getAlerts.mockResolvedValue({ alerts: [], limit: 10, offset: 0 });
  patchAlert.mockResolvedValue({});
});

afterEach(() => {
  cleanup();
});

function renderAlerts(role: string = "admin") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DisplayRoleProvider role={role}>
        <AlertsWorkspace />
      </DisplayRoleProvider>
    </QueryClientProvider>,
  );
}

describe("AlertsWorkspace", () => {
  it("requests alerts with the URL filter and shows only valid forward transitions", async () => {
    getAlerts.mockResolvedValue({
      alerts: [
        {
          alert_id: "alert-1",
          alert_type: "updated",
          document_id: "doc-1",
          title: "Guidance Example",
          previous_status: "Draft",
          current_status: "Final",
          previous_version_hash: "prev-hash",
          current_version_hash: "curr-hash",
          summary: "Summary text",
          status: "open",
          detected_at: "2026-08-10T12:00:00Z",
        },
      ],
      limit: 10,
      offset: 0,
    });

    renderAlerts("admin");

    expect(await screen.findByRole("heading", { name: /guidance alerts/i })).toBeInTheDocument();
    expect(getAlerts).toHaveBeenCalledWith(undefined, 10, 0);
    expect((await screen.findAllByRole("link", { name: /guidance example/i }))[0]).toHaveAttribute("href", "/documents/doc-1");
    expect((screen.getAllByRole("link", { name: /open key changes/i }))[0]).toHaveAttribute(
      "href",
      "/documents/doc-1?summary=key_changes#summary",
    );
    expect(screen.getAllByRole("button", { name: /acknowledge/i })[0]).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("hides mutation controls for non-admin display roles", async () => {
    getAlerts.mockResolvedValue({
      alerts: [
        {
          alert_id: "alert-2",
          alert_type: "updated",
          document_id: "doc-2",
          title: "Guidance Example",
          previous_status: "Draft",
          current_status: "Final",
          previous_version_hash: "prev-hash",
          current_version_hash: "curr-hash",
          summary: null,
          status: "open",
          detected_at: "2026-08-10T12:00:00Z",
        },
      ],
      limit: 10,
      offset: 0,
    });

    renderAlerts("researcher");

    expect((await screen.findAllByRole("link", { name: /guidance example/i }))[0]).toHaveAttribute("href", "/documents/doc-2");
    expect(screen.queryByRole("button", { name: /acknowledge/i })).not.toBeInTheDocument();
  });

  it("removes stale controls after a rejected transition", async () => {
    const user = userEvent.setup();
    getAlerts.mockResolvedValue({
      alerts: [
        {
          alert_id: "alert-3",
          alert_type: "updated",
          document_id: "doc-3",
          title: "Guidance Example",
          previous_status: "Draft",
          current_status: "Final",
          previous_version_hash: "prev-hash",
          current_version_hash: "curr-hash",
          summary: null,
          status: "open",
          detected_at: "2026-08-10T12:00:00Z",
        },
      ],
      limit: 10,
      offset: 0,
    });
    patchAlert.mockRejectedValue(new ApiClientError({ category: "validation", status: 422, message: "Validation failed" }));

    renderAlerts("admin");

    await user.click((await screen.findAllByRole("button", { name: /acknowledge/i }))[0]);

    expect(await screen.findByText(/alert update failed/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryAllByRole("button", { name: /acknowledge/i })).toHaveLength(0);
    });
  });
});