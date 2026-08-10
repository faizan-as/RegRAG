"use client";

import { useEffect, useMemo, useRef } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { createQueryClient } from "@/lib/query-client";
import { createSupabaseBrowserClient } from "@/lib/supabase/browser";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const queryClient = useMemo(() => createQueryClient(), []);
  const userIdRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    let cleanup = () => {};

    try {
      const supabase = createSupabaseBrowserClient();

      void supabase.auth.getSession().then(({ data }) => {
        userIdRef.current = data.session?.user.id ?? null;
      });

      const authSubscription = supabase.auth.onAuthStateChange(
        (_event, session: Session | null) => {
          const nextUserId = session?.user.id ?? null;
          if (userIdRef.current === undefined) {
            userIdRef.current = nextUserId;
          } else if (userIdRef.current !== nextUserId) {
            queryClient.clear();
            userIdRef.current = nextUserId;
          }
        },
      );

      cleanup = () => {
        authSubscription.data.subscription.unsubscribe();
      };
    } catch {
      // App can still render login configuration state without Supabase env.
    }

    return cleanup;
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delay={150}>
        {children}
        <Toaster closeButton richColors position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
