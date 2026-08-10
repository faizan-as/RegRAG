import { render } from "@testing-library/react";
import type { Session } from "@supabase/supabase-js";
import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/providers/app-providers";

const queryClient = new QueryClient();
const clear = vi.spyOn(queryClient, "clear");
let authStateChange: ((event: string, session: Session | null) => void) | undefined;

vi.mock("@/lib/query-client", () => ({
  createQueryClient: () => queryClient,
}));

vi.mock("@/lib/supabase/browser", () => ({
  createSupabaseBrowserClient: () => ({
    auth: {
      getSession: () => new Promise(() => {}),
      onAuthStateChange: (callback: (event: string, session: Session | null) => void) => {
        authStateChange = callback;
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      },
    },
  }),
}));

describe("AppProviders", () => {
  beforeEach(() => {
    clear.mockClear();
    authStateChange = undefined;
  });

  it("keeps query state during initial auth hydration and clears it on sign-out", () => {
    render(
      <AppProviders>
        <div>Application</div>
      </AppProviders>,
    );

    const initialSession = { user: { id: "user-1" } } as Session;
    authStateChange?.("INITIAL_SESSION", initialSession);
    expect(clear).not.toHaveBeenCalled();

    authStateChange?.("SIGNED_OUT", null);
    expect(clear).toHaveBeenCalledOnce();
  });
});