"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { EvidenceCard } from "@/components/citations/evidence-card";
import { ExportControls } from "@/components/summaries/export-controls";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { describeApiError, isApiClientError } from "@/lib/api/errors";

type SummaryResult = components["schemas"]["SummaryResult"];

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatVersionHash(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  return value.length > 12 ? `${value.slice(0, 12)}…` : value;
}

function summaryTypeLabel(summaryType: SummaryResult["summary_type"]): string {
  switch (summaryType) {
    case "key_requirements":
      return "Key requirements";
    case "key_changes":
      return "Key changes";
    default:
      return "Summary";
  }
}

function summaryStateLabel(summary: SummaryResult): { label: string; variant: "secondary" | "outline" | "destructive" } {
  if (summary.refused) {
    return { label: "Refused", variant: "outline" };
  }
  if (summary.faithfulness_passed === false) {
    return { label: "Faithfulness failed", variant: "destructive" };
  }
  if (summary.faithfulness_passed === true) {
    return { label: "Faithfulness passed", variant: "secondary" };
  }
  return { label: "Committed", variant: "secondary" };
}

function summaryErrorMessage(error: unknown): string {
  if (!isApiClientError(error)) {
    return "This summary is unavailable.";
  }

  if (error.category === "unauthorized" || error.category === "not_found") {
    return "This summary is unavailable.";
  }

  return describeApiError(error, {
    unauthenticated: "Sign in again to view this summary.",
    validation: "The summary identifier is invalid.",
    rateLimited: "Summary loading is temporarily rate limited.",
    unavailable: "The summary service is temporarily unavailable.",
  });
}

function CitationJumpButtons({ evidence }: { evidence: SummaryResult["evidence"] }) {
  if (!evidence || evidence.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Jump to citation">
      {evidence.map((card) => (
        <Button
          key={card.citation_id}
          type="button"
          variant="outline"
          size="xs"
          onClick={() => {
            document.getElementById(`citation-${card.citation_id}`)?.scrollIntoView({
              behavior: "smooth",
              block: "nearest",
            });
          }}
        >
          {card.citation_id}
        </Button>
      ))}
    </div>
  );
}

export function SummaryWorkspaceView({
  summary,
  documentTitle,
}: {
  summary: SummaryResult;
  documentTitle?: string;
}) {
  const state = summaryStateLabel(summary);
  const title = documentTitle ?? summary.evidence?.[0]?.title ?? summary.document_id;
  const sourceUrl = summary.evidence?.[0]?.source_url ?? null;
  const sourceStatus = summary.evidence?.[0]?.document_status ?? null;

  return (
    <article className="space-y-4">
      <header className="space-y-3 rounded-lg border border-border bg-surface-raised p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
              <Badge variant="outline" className="h-6">
                {summaryTypeLabel(summary.summary_type)}
              </Badge>
              <Badge variant={state.variant} className="h-6">
                {state.label}
              </Badge>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>Document {summary.document_id}</span>
              <span>•</span>
              <span>{summary.summary_type}</span>
              {sourceStatus ? (
                <>
                  <span>•</span>
                  <span>{sourceStatus}</span>
                </>
              ) : null}
              {sourceUrl ? (
                <>
                  <span>•</span>
                  <Link className="text-primary underline-offset-4 hover:underline" href={sourceUrl} target="_blank" rel="noreferrer">
                    FDA source
                  </Link>
                </>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" render={<Link href={`/documents/${encodeURIComponent(summary.document_id)}`} />}>
              Open document
            </Button>
            {summary.summary_id ? (
              <ExportControls
                target={{ kind: "summary", summaryId: summary.summary_id, filenameHint: `${summary.summary_type}-${summary.summary_id}.txt` }}
                actionLabel="Export summary"
                disabled={summary.refused && !summary.summary_id}
              />
            ) : null}
          </div>
        </div>

        <div className="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-md border border-border bg-background/70 px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Current version</p>
            <p className="mt-1 text-foreground">{formatVersionHash(summary.current_version_hash)}</p>
          </div>
          <div className="rounded-md border border-border bg-background/70 px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Previous version</p>
            <p className="mt-1 text-foreground">{formatVersionHash(summary.previous_version_hash)}</p>
          </div>
          <div className="rounded-md border border-border bg-background/70 px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Faithfulness</p>
            <p className="mt-1 text-foreground">
              {summary.faithfulness_passed === true
                ? "Passed"
                : summary.faithfulness_passed === false
                  ? "Failed"
                  : "Not reported"}
            </p>
          </div>
          <div className="rounded-md border border-border bg-background/70 px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Generated</p>
            <p className="mt-1 text-foreground">{formatDateTime(summary.generated_at)}</p>
          </div>
        </div>
      </header>

      {summary.refused ? (
        <Alert>
          <AlertTitle>Summary refused</AlertTitle>
          <AlertDescription>
            {summary.refusal_reason ?? "The workflow could not produce a grounded summary for this request."}
          </AlertDescription>
        </Alert>
      ) : null}

      <section className="rounded-lg border border-border bg-background/60 p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-foreground">Grounded text</h2>
          <Badge variant="outline" className="h-5">
            Markdown
          </Badge>
        </div>
        <div
          className={cn(
            "prose prose-sm max-w-none text-foreground",
            "[&_a]:text-primary [&_a]:underline-offset-4 [&_a:hover]:underline",
            "[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-px [&_code]:font-mono [&_code]:text-xs",
            "[&_pre]:overflow-auto [&_pre]:rounded [&_pre]:bg-muted [&_pre]:p-3",
          )}
        >
          <Markdown remarkPlugins={[remarkGfm]} skipHtml>
            {summary.text}
          </Markdown>
        </div>
      </section>

      {summary.refused ? (
        <section className="rounded-lg border border-border bg-background/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-foreground">Refinement</h2>
              <p className="text-sm text-muted-foreground">
                Return to the document workspace to choose another summary type or a different comparison version.
              </p>
            </div>
            <Button type="button" variant="outline" size="sm" render={<Link href={`/documents/${encodeURIComponent(summary.document_id)}#summary`} />}>
              Refine in document workspace
            </Button>
          </div>
        </section>
      ) : null}

      {summary.evidence && summary.evidence.length > 0 ? (
        <section className="space-y-3 rounded-lg border border-border bg-background/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-foreground">Evidence cards</h2>
            <CitationJumpButtons evidence={summary.evidence} />
          </div>
          <ol className="space-y-3">
            {summary.evidence.map((card) => (
              <li key={card.citation_id} id={`citation-${card.citation_id}`}>
                <EvidenceCard evidence={card} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </article>
  );
}

function SummaryWorkspaceLoading() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-28 rounded-lg" />
      <Skeleton className="h-64 rounded-lg" />
      <Skeleton className="h-48 rounded-lg" />
    </div>
  );
}

function SummaryWorkspaceError({ error }: { error: unknown }) {
  return (
    <Alert variant="destructive">
      <AlertTitle>Summary unavailable</AlertTitle>
      <AlertDescription>{summaryErrorMessage(error)}</AlertDescription>
    </Alert>
  );
}

export function SummaryWorkspace({ summaryId }: { summaryId: string }) {
  const apiClient = useMemo(() => createApiClient(), []);

  const summaryQuery = useQuery({
    queryKey: ["summary", summaryId],
    queryFn: () => apiClient.getSummary(summaryId),
  });

  if (summaryQuery.isLoading) {
    return <SummaryWorkspaceLoading />;
  }

  if (summaryQuery.isError) {
    return <SummaryWorkspaceError error={summaryQuery.error} />;
  }

  if (!summaryQuery.data) {
    return <SummaryWorkspaceError error={new Error("Summary data is unavailable.")} />;
  }

  return <SummaryWorkspaceView summary={summaryQuery.data} />;
}