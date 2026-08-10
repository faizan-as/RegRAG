import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-svh max-w-[1200px] items-center justify-center px-3 py-8">
      <section className="w-full max-w-md rounded-lg border border-border bg-card p-5 text-center shadow-sm">
        <h1 className="text-xl font-semibold">Route not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The requested workspace route could not be resolved.
        </p>
        <div className="mt-4 flex justify-center">
          <Button render={<Link href="/research" />} className="h-9">
            Return to research
          </Button>
        </div>
      </section>
    </main>
  );
}
