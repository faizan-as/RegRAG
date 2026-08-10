"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertCircleIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { createApiClient } from "@/lib/api/client";
import { describeApiError, isApiClientError } from "@/lib/api/errors";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

const DEFAULT_LIMIT = 20;

function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

function describeAuditError(error: unknown): string {
  if (!isApiClientError(error)) {
    return "The audit workspace could not load.";
  }

  return describeApiError(error, {
    unauthenticated: "Sign in again to view audit events.",
    unauthorized: "Admin access is required to inspect audit events.",
    validation: "Review the selected audit filters and try again.",
    rateLimited: "Audit inspection is temporarily rate limited.",
    unavailable: "Audit inspection is temporarily unavailable.",
  });
}

function payloadText(payload: Record<string, unknown>): string {
  return JSON.stringify(payload, null, 2);
}

function AuditLoadingState() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton key={index} className="h-12 w-full rounded-lg" />
      ))}
    </div>
  );
}

function PayloadDialog({ payload, eventId }: { payload: Record<string, unknown>; eventId: string }) {
  return (
    <Dialog>
      <DialogTrigger render={<Button type="button" variant="ghost" size="xs" />}>View payload</DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Redacted payload</DialogTitle>
          <DialogDescription>Structured JSON payload for audit event {eventId}.</DialogDescription>
        </DialogHeader>
        <pre className="max-h-[60svh] overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 whitespace-pre-wrap break-words text-foreground">
          {payloadText(payload)}
        </pre>
      </DialogContent>
    </Dialog>
  );
}

function AuditErrorState({ error }: { error: unknown }) {
  const accessDenied = isApiClientError(error) && error.status === 403;
  return (
    <Alert variant={accessDenied ? "destructive" : undefined}>
      <AlertCircleIcon />
      <AlertTitle>{accessDenied ? "Access denied" : "Audit unavailable"}</AlertTitle>
      <AlertDescription>{describeAuditError(error)}</AlertDescription>
    </Alert>
  );
}

export function AuditWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const apiClient = useMemo(() => createApiClient(), []);

  const filters = useMemo(
    () => ({
      event_type: searchParams.get("event_type") ?? undefined,
      user_id: searchParams.get("user_id") ?? undefined,
      session_id: searchParams.get("session_id") ?? undefined,
      route: searchParams.get("route") ?? undefined,
      created_from: searchParams.get("created_from") ?? undefined,
      created_to: searchParams.get("created_to") ?? undefined,
    }),
    [searchParams],
  );
  const limit = useMemo(() => Math.max(1, Number.parseInt(searchParams.get("limit") ?? `${DEFAULT_LIMIT}`, 10) || DEFAULT_LIMIT), [searchParams]);
  const offset = useMemo(() => Math.max(0, Number.parseInt(searchParams.get("offset") ?? "0", 10) || 0), [searchParams]);

  const auditQuery = useQuery({
    queryKey: ["audit", filters, limit, offset],
    queryFn: () => apiClient.getAudit(filters, limit, offset),
  });

  const events = auditQuery.data?.events ?? [];
  const responseLimit = auditQuery.data?.limit ?? limit;
  const responseOffset = auditQuery.data?.offset ?? offset;

  const updateSearchParams = (next: URLSearchParams) => {
    router.push(next.toString() ? `${pathname}?${next.toString()}` : pathname);
  };

  const setFilter = (name: string, value: string) => {
    const next = new URLSearchParams(searchParams.toString());
    if (value.trim()) {
      next.set(name, value.trim());
    } else {
      next.delete(name);
    }
    next.set("offset", "0");
    next.set("limit", String(responseLimit));
    updateSearchParams(next);
  };

  const goToOffset = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("offset", String(Math.max(0, nextOffset)));
    next.set("limit", String(responseLimit));
    updateSearchParams(next);
  };

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-3 sm:p-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold">Audit inspection</h1>
            <p className="text-sm text-muted-foreground">Filter redacted audit events by event type, user, session, route, and time.</p>
          </div>
          <Badge variant="secondary" className="h-6">Admin</Badge>
        </div>

        <div className="grid gap-2 md:grid-cols-3 xl:grid-cols-6">
          <Input aria-label="Event type" placeholder="Event type" defaultValue={filters.event_type ?? ""} onChange={(event) => setFilter("event_type", event.currentTarget.value)} />
          <Input aria-label="User id" placeholder="User id" defaultValue={filters.user_id ?? ""} onChange={(event) => setFilter("user_id", event.currentTarget.value)} />
          <Input aria-label="Session id" placeholder="Session id" defaultValue={filters.session_id ?? ""} onChange={(event) => setFilter("session_id", event.currentTarget.value)} />
          <Input aria-label="Route" placeholder="Route" defaultValue={filters.route ?? ""} onChange={(event) => setFilter("route", event.currentTarget.value)} />
          <Input aria-label="Created from" type="date" defaultValue={filters.created_from ?? ""} onChange={(event) => setFilter("created_from", event.currentTarget.value)} />
          <Input aria-label="Created to" type="date" defaultValue={filters.created_to ?? ""} onChange={(event) => setFilter("created_to", event.currentTarget.value)} />
        </div>

        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => goToOffset(responseOffset - responseLimit)} disabled={responseOffset <= 0}>
            <ChevronLeftIcon className="size-4" />
            Previous
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => goToOffset(responseOffset + responseLimit)} disabled={events.length < responseLimit}>
            Next
            <ChevronRightIcon className="size-4" />
          </Button>
        </div>
      </header>

      {auditQuery.isLoading ? <AuditLoadingState /> : null}

      {auditQuery.isError ? <AuditErrorState error={auditQuery.error} /> : null}

      {!auditQuery.isLoading && !auditQuery.isError ? (
        events.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">Showing {responseOffset + 1}-{responseOffset + events.length}</div>

            <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/30 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Event</th>
                    <th className="px-3 py-2">User</th>
                    <th className="px-3 py-2">Session</th>
                    <th className="px-3 py-2">Route</th>
                    <th className="px-3 py-2">Request</th>
                    <th className="px-3 py-2">Time</th>
                    <th className="px-3 py-2 text-right">Payload</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.event_id} className="border-b border-border last:border-b-0 align-top hover:bg-muted/30">
                      <td className="px-3 py-3"><Badge variant="outline" className="h-5">{event.event_type}</Badge></td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">{event.user_id ?? "-"}</td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">{event.session_id ?? "-"}</td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">{event.route ?? "-"}</td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">{event.request_id ?? "-"}</td>
                      <td className="px-3 py-3 text-xs text-muted-foreground">{formatDateTime(event.created_at)}</td>
                      <td className="px-3 py-3 text-right"><PayloadDialog payload={event.payload} eventId={event.event_id} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <ul className="divide-y divide-border md:hidden" role="list" aria-label="Audit events">
              {events.map((event) => (
                <li key={event.event_id} className="space-y-2 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="outline" className="h-5">{event.event_type}</Badge>
                    <span className="text-muted-foreground">{formatDateTime(event.created_at)}</span>
                  </div>
                  <div className="grid grid-cols-1 gap-1 text-xs text-muted-foreground sm:grid-cols-2">
                    <span>User {event.user_id ?? "-"}</span>
                    <span>Session {event.session_id ?? "-"}</span>
                    <span className="sm:col-span-2">Route {event.route ?? "-"}</span>
                    <span className="sm:col-span-2">Request {event.request_id ?? "-"}</span>
                  </div>
                  <PayloadDialog payload={event.payload} eventId={event.event_id} />
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">No audit events match the current filter.</div>
        )
      ) : null}
    </section>
  );
}