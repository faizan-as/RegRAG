"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { DownloadIcon, Loader2Icon } from "lucide-react";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { downloadExportWithAuth } from "@/lib/api/download";
import { describeApiError, isApiClientError } from "@/lib/api/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

type ExportFormat = components["schemas"]["ExportFormat"];
type ExportRequest = components["schemas"]["ExportRequest"];
type ExportResult = components["schemas"]["ExportResult"];

type SummaryExportTarget = {
  kind: "summary";
  summaryId: string;
  filenameHint?: string;
};

type TranscriptExportTarget = {
  kind: "transcript";
  sessionId: string;
  filenameHint?: string;
};

export type ExportTarget = SummaryExportTarget | TranscriptExportTarget;

const MAX_PENDING_POLLS = 6;

function extensionForFormat(format: ExportFormat): string {
  return format === "pdf" ? "pdf" : format === "docx" ? "docx" : "txt";
}

function fallbackExportName(target: ExportTarget, format: ExportFormat): string {
  const base = target.kind === "summary" ? `summary-${target.summaryId}` : `transcript-${target.sessionId}`;
  return `${base}.${extensionForFormat(format)}`;
}

export function buildExportRequest(target: ExportTarget, exportFormat: ExportFormat): ExportRequest {
  if (target.kind === "summary") {
    return {
      export_type: "summary",
      export_format: exportFormat,
      summary_id: target.summaryId,
    };
  }

  return {
    export_type: "transcript",
    export_format: exportFormat,
    session_id: target.sessionId,
  };
}

function describeExportError(error: unknown): string {
  if (!isApiClientError(error)) {
    return "The export could not be completed.";
  }

  return describeApiError(error, {
    unauthenticated: "Sign in again to export this record.",
    unauthorized: "You do not have access to export this record.",
    notFound: "The export source is no longer available.",
    validation: "The export request needs a valid source record.",
    rateLimited: "Export requests are temporarily rate limited.",
    unavailable: "Exporting is temporarily unavailable.",
  });
}

export function ExportControls({
  target,
  actionLabel,
  className,
  disabled = false,
}: {
  target: ExportTarget;
  actionLabel: string;
  className?: string;
  disabled?: boolean;
}) {
  const apiClient = useMemo(() => createApiClient(), []);
  const [format, setFormat] = useState<ExportFormat>("text");
  const [pendingExportId, setPendingExportId] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const handledExportRef = useRef<string | null>(null);

  const handleExportResult = useCallback(
    async (result: ExportResult): Promise<void> => {
      if (result.status === "pending") {
        setPendingExportId(result.export_id);
        setPollCount(0);
        setMessage("Preparing export.");
        handledExportRef.current = null;
        return;
      }

      setPendingExportId(null);
      setPollCount(0);
      handledExportRef.current = null;

      if (result.status === "failed") {
        setMessage(result.error_message ?? "The export failed before a file was produced.");
        return;
      }

      try {
        const filename = await downloadExportWithAuth({
          apiClient,
          exportId: result.export_id,
          fallbackFilename: target.filenameHint ?? fallbackExportName(target, format),
        });
        setMessage(`Downloaded ${filename}.`);
      } catch (error) {
        setErrorMessage(describeExportError(error));
      }
    },
    [apiClient, format, target],
  );

  const createExportMutation = useMutation({
    mutationFn: async () => apiClient.createExport(buildExportRequest(target, format)),
    onMutate: () => {
      setMessage(null);
      setErrorMessage(null);
    },
    onError: (error) => {
      setErrorMessage(describeExportError(error));
    },
    onSuccess: async (result) => {
      await handleExportResult(result);
    },
  });

  const pendingExportQuery = useQuery({
    queryKey: ["export", target.kind, pendingExportId],
    queryFn: async () => apiClient.getExport(pendingExportId ?? ""),
    enabled: Boolean(pendingExportId),
    retry: false,
    refetchInterval: pendingExportId && pollCount < MAX_PENDING_POLLS ? 2000 : false,
  });

  useEffect(() => {
    if (!pendingExportQuery.data || !pendingExportId) {
      return;
    }

    const exportId = pendingExportQuery.data.export_id;
    const updatedAt = pendingExportQuery.dataUpdatedAt;
    const handledKey = `${exportId}:${updatedAt}`;
    if (handledExportRef.current === handledKey) {
      return;
    }
    handledExportRef.current = handledKey;

    if (pendingExportQuery.data.status === "pending") {
      if (pollCount >= MAX_PENDING_POLLS) {
        setPendingExportId(null);
        setMessage("The export is still processing. Refresh this view later to download it.");
      } else {
        setPollCount((current) => current + 1);
      }
      return;
    }

    void handleExportResult(pendingExportQuery.data);
  }, [handleExportResult, pendingExportId, pendingExportQuery.data, pendingExportQuery.dataUpdatedAt, pollCount]);

  const isBusy = createExportMutation.isPending || Boolean(pendingExportId);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={format}
          onValueChange={(value) => setFormat(value as ExportFormat)}
          disabled={disabled || isBusy}
        >
          <SelectTrigger aria-label="Export format" className="min-w-28" size="sm">
            <SelectValue placeholder="Format" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="text">Text</SelectItem>
            <SelectItem value="docx">DOCX</SelectItem>
            <SelectItem value="pdf">PDF</SelectItem>
          </SelectContent>
        </Select>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => createExportMutation.mutate()}
          disabled={disabled || isBusy}
        >
          {isBusy ? <Loader2Icon className="size-4 animate-spin" /> : <DownloadIcon className="size-4" />}
          {actionLabel}
        </Button>

        {pendingExportId ? (
          <Badge variant="outline" className="h-6">
            Pending
          </Badge>
        ) : null}
      </div>

      {message ? <p className="text-xs text-muted-foreground">{message}</p> : null}
      {errorMessage ? (
        <p role="alert" className="text-xs text-destructive">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}