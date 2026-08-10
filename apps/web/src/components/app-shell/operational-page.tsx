import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";

type OperationalPageProps = {
  title: string;
  subtitle: string;
  status?: string;
  children?: ReactNode;
};

export function OperationalPage({ title, subtitle, status = "MVP foundation", children }: OperationalPageProps) {
  return (
    <section className="rounded-lg border border-border bg-card p-4 shadow-sm sm:p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-lg font-semibold sm:text-xl">{title}</h1>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>
        <Badge variant="secondary" className="h-6">{status}</Badge>
      </div>
      <div className="space-y-3 text-sm text-muted-foreground">{children}</div>
    </section>
  );
}
