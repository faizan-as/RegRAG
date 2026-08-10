"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { BellRingIcon, CheckCircle2Icon, ChevronLeftIcon, ChevronRightIcon, RotateCwIcon } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { describeApiError, isApiClientError } from "@/lib/api/errors";
import { useDisplayRole } from "@/components/app-shell/display-role-context";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

type AlertResponse = components["schemas"]["AlertResponse"];
type AlertStatus = components["schemas"]["AlertStatus"];

const DEFAULT_LIMIT = 10;

function clampLimit(value: number): number {
  return Math.min(Math.max(Math.trunc(value), 1), 50);
}

function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return value;
  }
}

function describeAlertsError(error: unknown): string {
  if (!isApiClientError(error)) {
    return "The alerts workspace could not load.";
  }

  return describeApiError(error, {
    unauthenticated: "Sign in again to view alerts.",
    unauthorized: "You do not have access to manage alerts.",
    validation: "Review the selected filter or alert transition and try again.",
    rateLimited: "Alerts are temporarily rate limited.",
    unavailable: "Alerts are temporarily unavailable.",
  });
}

function alertStatusVariant(status: AlertStatus): "default" | "secondary" | "outline" {
  if (status === "acknowledged") {
    return "secondary";
  }
  if (status === "resolved") {
    return "outline";
  }
  return "default";
}

function alertActionStatus(current: AlertStatus): AlertStatus | null {
  if (current === "open") {
    return "acknowledged";
  }
  if (current === "acknowledged") {
    return "resolved";
  }
  return null;
}

function keyChangesHref(alert: AlertResponse): string | null {
  if (!alert.previous_version_hash || !alert.current_version_hash) {
    return null;
  }
  return `/documents/${encodeURIComponent(alert.document_id)}?summary=key_changes#summary`;
}

function AlertControls({
  alert,
  disabled,
  onTransition,
}: {
  alert: AlertResponse;
  disabled: boolean;
  onTransition: (alertId: string, nextStatus: AlertStatus) => void;
}) {
  const nextStatus = alertActionStatus(alert.status);
  if (!nextStatus) {
    return null;
  }

  return (
    <Button type="button" variant="outline" size="sm" onClick={() => onTransition(alert.alert_id, nextStatus)} disabled={disabled}>
      {nextStatus === "acknowledged" ? "Acknowledge" : "Resolve"}
    </Button>
  );
}

function AlertsSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-10 w-full rounded-lg" />
      {Array.from({ length: 5 }).map((_, index) => (
        <Skeleton key={index} className="h-16 w-full rounded-lg" />
      ))}
    </div>
  );
}

export function AlertsWorkspace() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const apiClient = useMemo(() => createApiClient(), []);
  const displayRole = useDisplayRole().role;
  const canMutate = displayRole === "admin";
  const [disabledAlertIds, setDisabledAlertIds] = useState<Set<string>>(new Set());

  const status = useMemo<AlertStatus | "all">(() => {
    const value = searchParams.get("status");
    return value === "open" || value === "acknowledged" || value === "resolved" ? value : "all";
  }, [searchParams]);

  const limit = useMemo(() => clampLimit(Number.parseInt(searchParams.get("limit") ?? `${DEFAULT_LIMIT}`, 10) || DEFAULT_LIMIT), [searchParams]);
  const offset = useMemo(() => Math.max(0, Number.parseInt(searchParams.get("offset") ?? "0", 10) || 0), [searchParams]);

  const alertsQuery = useQuery({
    queryKey: ["alerts", status, limit, offset],
    queryFn: () => apiClient.getAlerts(status === "all" ? undefined : status, limit, offset),
  });

  const transitionMutation = useMutation({
    mutationFn: async ({ alertId, nextStatus }: { alertId: string; nextStatus: AlertStatus }) =>
      apiClient.patchAlert(alertId, nextStatus),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
    onError: (error, variables) => {
      if (isApiClientError(error) && (error.status === 403 || error.status === 422)) {
        setDisabledAlertIds((current) => new Set(current).add(variables.alertId));
      }
    },
  });

  const alerts = alertsQuery.data?.alerts ?? [];
  const responseLimit = alertsQuery.data?.limit ?? limit;
  const responseOffset = alertsQuery.data?.offset ?? offset;
  const canGoPrevious = responseOffset > 0;
  const canGoNext = alerts.length === responseLimit && responseLimit > 0;

  const updateSearchParams = (next: URLSearchParams) => {
    router.push(next.toString() ? `${pathname}?${next.toString()}` : pathname);
  };

  const setStatusFilter = (nextStatus: AlertStatus | "all") => {
    const next = new URLSearchParams(searchParams.toString());
    if (nextStatus === "all") {
      next.delete("status");
    } else {
      next.set("status", nextStatus);
    }
    next.set("offset", "0");
    next.set("limit", String(responseLimit));
    updateSearchParams(next);
  };

  const goToOffset = (nextOffset: number) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set("offset", String(Math.max(0, nextOffset)));
    next.set("limit", String(responseLimit));
    if (status !== "all") {
      next.set("status", status);
    }
    updateSearchParams(next);
  };

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-3 sm:p-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold">Guidance alerts</h1>
            <p className="text-sm text-muted-foreground">Review new, updated, and withdrawn FDA guidance alerts.</p>
          </div>
          <Badge variant="secondary" className="h-6">{displayRole}</Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Select value={status} onValueChange={(value) => setStatusFilter(value as AlertStatus | "all")}>
            <SelectTrigger aria-label="Filter alerts by status" className="w-full sm:w-48" size="sm">
              <SelectValue placeholder="Status filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="acknowledged">Acknowledged</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>

          <Button type="button" variant="outline" size="sm" onClick={() => alertsQuery.refetch()}>
            <RotateCwIcon className="size-4" />
            Refresh
          </Button>

          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => goToOffset(responseOffset - responseLimit)} disabled={!canGoPrevious}>
              <ChevronLeftIcon className="size-4" />
              Previous
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => goToOffset(responseOffset + responseLimit)} disabled={!canGoNext}>
              Next
              <ChevronRightIcon className="size-4" />
            </Button>
          </div>
        </div>
      </header>

      {alertsQuery.isLoading ? <AlertsSkeleton /> : null}

      {alertsQuery.isError ? (
        <Alert variant={isApiClientError(alertsQuery.error) && alertsQuery.error.status === 403 ? "destructive" : undefined}>
          <BellRingIcon />
          <AlertTitle>{isApiClientError(alertsQuery.error) && alertsQuery.error.status === 403 ? "Access denied" : "Alerts unavailable"}</AlertTitle>
          <AlertDescription>{describeAlertsError(alertsQuery.error)}</AlertDescription>
        </Alert>
      ) : null}

      {!alertsQuery.isLoading && !alertsQuery.isError ? (
        alerts.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs text-muted-foreground">Showing {responseOffset + 1}-{responseOffset + alerts.length}</div>

            <div className="hidden overflow-x-auto rounded-lg border border-border md:block">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/30 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Title</th>
                    <th className="px-3 py-2">Prior / current</th>
                    <th className="px-3 py-2">Detected</th>
                    <th className="px-3 py-2">Versions</th>
                    <th className="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => {
                    const keyChangesUrl = keyChangesHref(alert);
                    const disabled = disabledAlertIds.has(alert.alert_id);
                    return (
                      <tr key={alert.alert_id} className="border-b border-border last:border-b-0 align-top hover:bg-muted/30">
                        <td className="px-3 py-3"><Badge variant="outline" className="h-5">{alert.alert_type}</Badge></td>
                        <td className="px-3 py-3"><Badge variant={alertStatusVariant(alert.status)} className="h-5">{alert.status}</Badge></td>
                        <td className="px-3 py-3">
                          <div className="space-y-1">
                            <Link className="font-medium text-foreground underline-offset-4 hover:underline" href={`/documents/${encodeURIComponent(alert.document_id)}`}>
                              {alert.title}
                            </Link>
                            {alert.summary ? <p className="max-w-[42rem] text-xs text-muted-foreground">{alert.summary}</p> : null}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-xs text-muted-foreground">
                          <div className="flex flex-col gap-1">
                            <span>Previous: <span className="font-medium text-foreground">{alert.previous_status ?? "-"}</span></span>
                            <span>Current: <span className="font-medium text-foreground">{alert.current_status ?? "-"}</span></span>
                          </div>
                        </td>
                        <td className="px-3 py-3 text-xs text-muted-foreground">{formatDateTime(alert.detected_at)}</td>
                        <td className="px-3 py-3 text-xs text-muted-foreground">
                          <div className="flex flex-col gap-1">
                            <span>Prior: <span className="font-medium text-foreground">{alert.previous_version_hash ? alert.previous_version_hash.slice(0, 12) : "-"}</span></span>
                            <span>Current: <span className="font-medium text-foreground">{alert.current_version_hash ? alert.current_version_hash.slice(0, 12) : "-"}</span></span>
                            {keyChangesUrl ? <Button type="button" variant="ghost" size="xs" render={<Link href={keyChangesUrl} />}>Open key changes</Button> : null}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right">
                          {canMutate && !disabled ? (
                            <AlertControls alert={alert} disabled={false} onTransition={(alertId, nextStatus) => transitionMutation.mutate({ alertId, nextStatus })} />
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <ul className="divide-y divide-border md:hidden" role="list" aria-label="Alerts">
              {alerts.map((alert) => {
                const keyChangesUrl = keyChangesHref(alert);
                const disabled = disabledAlertIds.has(alert.alert_id);
                return (
                  <li key={alert.alert_id} className="space-y-3 py-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <Badge variant="outline" className="h-5">{alert.alert_type}</Badge>
                      <Badge variant={alertStatusVariant(alert.status)} className="h-5">{alert.status}</Badge>
                      <span className="text-muted-foreground">{formatDateTime(alert.detected_at)}</span>
                    </div>
                    <div className="space-y-1">
                      <Link className="block font-medium text-foreground underline-offset-4 hover:underline" href={`/documents/${encodeURIComponent(alert.document_id)}`}>
                        {alert.title}
                      </Link>
                      {alert.summary ? <p className="text-sm text-muted-foreground">{alert.summary}</p> : null}
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>Previous {alert.previous_status ?? "-"}</span>
                      <span>Current {alert.current_status ?? "-"}</span>
                      <span>Prior {alert.previous_version_hash ? alert.previous_version_hash.slice(0, 12) : "-"}</span>
                      <span>Current {alert.current_version_hash ? alert.current_version_hash.slice(0, 12) : "-"}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {keyChangesUrl ? <Button type="button" variant="outline" size="sm" render={<Link href={keyChangesUrl} />}>Open key changes</Button> : null}
                      {canMutate && !disabled ? (
                        <AlertControls alert={alert} disabled={false} onTransition={(alertId, nextStatus) => transitionMutation.mutate({ alertId, nextStatus })} />
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">No alerts match the current filter.</div>
        )
      ) : null}

      {transitionMutation.isError ? (
        <Alert variant="destructive">
          <CheckCircle2Icon />
          <AlertTitle>Alert update failed</AlertTitle>
          <AlertDescription>{describeAlertsError(transitionMutation.error)}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}