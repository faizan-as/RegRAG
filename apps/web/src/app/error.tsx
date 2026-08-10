"use client";

import { useEffect } from "react";
import { AlertTriangleIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-svh max-w-[1200px] items-center justify-center px-3 py-8">
      <section className="w-full max-w-md rounded-lg border border-withdrawn/40 bg-card p-5 shadow-sm">
        <div className="mb-3 inline-flex items-center gap-2 text-withdrawn">
          <AlertTriangleIcon className="size-4" />
          <h1 className="text-lg font-semibold text-foreground">Application error</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          A recoverable interface error occurred. Retry this operation or return to a stable route.
        </p>
        <Button type="button" variant="outline" className="mt-4 h-9" onClick={reset}>
          Retry
        </Button>
      </section>
    </main>
  );
}
