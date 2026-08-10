"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { GitCompareArrowsIcon, Loader2Icon, SparklesIcon } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { describeApiError, isApiClientError } from "@/lib/api/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type SummaryType = components["schemas"]["SummaryType"];
type DocumentVersionResponse = components["schemas"]["DocumentVersionResponse"];
type SummaryResult = components["schemas"]["SummaryResult"];

export function getComparisonVersionOptions(
  versions: DocumentVersionResponse[],
  currentVersionHash: string,
): DocumentVersionResponse[] {
  return versions.filter((version) => version.version_hash !== currentVersionHash);
}

function formatVersionLabel(version: DocumentVersionResponse): string {
  const createdAt = version.created_at
    ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(version.created_at))
    : "Unknown date";
  return `${version.version_hash.slice(0, 12)} · ${createdAt}`;
}

function summaryTypeLabel(summaryType: SummaryType): string {
  switch (summaryType) {
    case "key_requirements":
      return "Key requirements";
    case "key_changes":
      return "Key changes";
    default:
      return "Summary";
  }
}

function describeSummaryError(error: unknown): string {
  if (!isApiClientError(error)) {
    return "The summary could not be generated.";
  }

  return describeApiError(error, {
    unauthenticated: "Sign in again to generate this summary.",
    unauthorized: "You do not have access to generate this summary.",
    notFound: "The source document is not available.",
    validation: "Choose a valid summary type and prior version.",
    rateLimited: "Summary generation is temporarily rate limited.",
    unavailable: "Summary generation is temporarily unavailable.",
  });
}

export function SummaryGenerationPanel({
  documentId,
  currentVersionHash,
  versions,
  summaryType,
  onSummaryTypeChange,
  onSummaryCreated,
}: {
  documentId: string;
  currentVersionHash: string;
  versions: DocumentVersionResponse[];
  summaryType: SummaryType;
  onSummaryTypeChange: (summaryType: SummaryType) => void;
  onSummaryCreated: (summaryId: string) => void;
}) {
  const apiClient = useMemo(() => createApiClient(), []);
  const comparisonVersions = useMemo(
    () => getComparisonVersionOptions(versions, currentVersionHash),
    [versions, currentVersionHash],
  );
  const [compareVersionHash, setCompareVersionHash] = useState<string>(comparisonVersions[0]?.version_hash ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (summaryType !== "key_changes") {
      return;
    }

    if (!compareVersionHash && comparisonVersions[0]) {
      setCompareVersionHash(comparisonVersions[0].version_hash);
    }
  }, [compareVersionHash, comparisonVersions, summaryType]);

  useEffect(() => {
    if (!comparisonVersions.some((version) => version.version_hash === compareVersionHash)) {
      setCompareVersionHash(comparisonVersions[0]?.version_hash ?? "");
    }
  }, [comparisonVersions, compareVersionHash]);

  const createSummaryMutation = useMutation({
    mutationFn: async () =>
      apiClient.createSummary({
        document_id: documentId,
        summary_type: summaryType,
        compare_version_hash: summaryType === "key_changes" ? compareVersionHash : null,
      }),
    onMutate: () => {
      setMessage(null);
      setErrorMessage(null);
    },
    onError: (error) => {
      setErrorMessage(describeSummaryError(error));
    },
    onSuccess: (result: SummaryResult) => {
      const summaryId = result.summary_id;
      if (!summaryId) {
        setErrorMessage("The summary completed without a durable summary id.");
        return;
      }

      setMessage(result.refused ? "The summary was refused and saved as a durable result." : "Summary generated.");
      onSummaryCreated(summaryId);
    },
  });

  const hasPriorVersion = comparisonVersions.length > 0;
  const canSubmit = summaryType !== "key_changes" || (hasPriorVersion && Boolean(compareVersionHash));

  return (
    <section className="space-y-3 rounded-lg border border-border bg-background/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-foreground">Grounded summaries</h2>
            <Badge variant="outline" className="h-5">
              Durable
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Generate a server-owned summary, key requirements list, or version comparison from grounded evidence.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant={summaryType === "summary" ? "secondary" : "outline"}
            size="sm"
            onClick={() => onSummaryTypeChange("summary")}
          >
            <SparklesIcon className="size-4" />
            Summary
          </Button>
          <Button
            type="button"
            variant={summaryType === "key_requirements" ? "secondary" : "outline"}
            size="sm"
            onClick={() => onSummaryTypeChange("key_requirements")}
          >
            <SparklesIcon className="size-4" />
            Key requirements
          </Button>
          <Button
            type="button"
            variant={summaryType === "key_changes" ? "secondary" : "outline"}
            size="sm"
            onClick={() => onSummaryTypeChange("key_changes")}
          >
            <GitCompareArrowsIcon className="size-4" />
            Key changes
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="outline" className="h-5">
              Current {currentVersionHash.slice(0, 12)}
            </Badge>
            <Badge variant="outline" className="h-5">
              {summaryTypeLabel(summaryType)}
            </Badge>
          </div>

          {summaryType === "key_changes" ? (
            <div className="space-y-2">
              <label className="text-xs font-medium text-foreground" htmlFor="summary-compare-version">
                Compare against a prior version
              </label>
              <Select
                value={compareVersionHash || ""}
                onValueChange={(value) => setCompareVersionHash(value ?? "")}
                disabled={!hasPriorVersion || createSummaryMutation.isPending}
              >
                <SelectTrigger id="summary-compare-version" className="w-full md:max-w-md" size="sm">
                  <SelectValue placeholder="Select a prior version" />
                </SelectTrigger>
                <SelectContent>
                  {comparisonVersions.map((version) => (
                    <SelectItem key={version.version_hash} value={version.version_hash}>
                      {formatVersionLabel(version)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!hasPriorVersion ? (
                <p className="text-xs text-muted-foreground">
                  No prior version is available yet, so key changes cannot be generated.
                </p>
              ) : null}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              The current version will be used as the grounding source.
            </p>
          )}
        </div>

        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={() => createSummaryMutation.mutate()}
          disabled={!canSubmit || createSummaryMutation.isPending}
        >
          {createSummaryMutation.isPending ? <Loader2Icon className="size-4 animate-spin" /> : <SparklesIcon className="size-4" />}
          Generate
        </Button>
      </div>

      {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
      {errorMessage ? (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage}
        </p>
      ) : null}
    </section>
  );
}