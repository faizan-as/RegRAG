"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
} from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  ArrowLeftIcon,
  ArrowRightIcon,
  DownloadIcon,
  FileTextIcon,
  Layers3Icon,
  MenuIcon,
  PanelLeftIcon,
  PanelRightIcon,
} from "lucide-react";
import type { components } from "@/lib/api/schema";
import { createApiClient } from "@/lib/api/client";
import { createAuthenticatedBlobResource, downloadArtifactWithAuth } from "@/lib/api/download";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { SummaryGenerationPanel } from "@/components/summaries/summary-actions";

type DocumentArtifact = components["schemas"]["DocumentArtifact"];
type DocumentMetadata = components["schemas"]["DocumentMetadata"];
type SectionNavigationEntry = components["schemas"]["SectionNavigationEntry"];
type PassageResponse = components["schemas"]["PassageResponse"];
type DocumentVersionResponse = components["schemas"]["DocumentVersionResponse"];
type DocumentStatus = components["schemas"]["DocumentStatus"];
type SummaryType = components["schemas"]["SummaryType"];

type AuthenticatedBlobResource = Awaited<ReturnType<typeof createAuthenticatedBlobResource>>;

type PassageVerification = {
  routeVerified: boolean;
  versionMatched: boolean | null;
  pageMatched: boolean | null;
  sectionMatched: boolean | null;
  textMatched: boolean | null;
  mismatchReasons: string[];
  label: string;
};

type DocumentWorkspaceViewProps = {
  documentId: string;
  metadata: DocumentMetadata;
  sections: SectionNavigationEntry[];
  versions: DocumentVersionResponse[];
  artifacts: DocumentArtifact[];
  routeState: {
    chunkId?: string;
    page?: number | null;
    version?: string | null;
    section?: string | null;
  };
  passage?: PassageResponse;
  passageVerification?: PassageVerification;
  artifactResource?: AuthenticatedBlobResource | null | undefined;
  artifactError?: string | null;
  selectedArtifactId?: string | null;
  selectedSectionId?: string | null;
  onSelectArtifact: (artifactId: string) => void;
  onNavigatePage: (page: number) => void;
  onNavigateSection: (section: SectionNavigationEntry) => void;
  onNavigateVersion: (versionHash: string) => void;
  onDownloadArtifact: () => void;
  onOpenArtifact: () => void;
  summaryType: SummaryType;
  onSummaryTypeChange: (summaryType: SummaryType) => void;
  summarySectionRef: React.RefObject<HTMLElement | null>;
  onSummaryCreated: (summaryId: string) => void;
};

type PdfRuntime = {
  Document: ComponentType<Record<string, unknown>>;
  Page: ComponentType<Record<string, unknown>>;
  pdfjs: {
    GlobalWorkerOptions: {
      workerSrc: string;
    };
  };
};

const PDF_WORKER_SRC = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

function safeLower(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

export function normalizeDocumentText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
  } catch {
    return value;
  }
}

function formatStatus(status: DocumentStatus): string {
  return status;
}

export function selectPreferredArtifact(artifacts: DocumentArtifact[]): DocumentArtifact | undefined {
  const pdfArtifact = artifacts.find((artifact) => safeLower(artifact.content_type).includes("pdf"));
  if (pdfArtifact) {
    return pdfArtifact;
  }

  const htmlArtifact = artifacts.find((artifact) => safeLower(artifact.content_type).includes("html"));
  if (htmlArtifact) {
    return htmlArtifact;
  }

  return artifacts[0];
}

export function verifyPassageTarget(args: {
  documentId: string;
  routeVersion?: string | null;
  routePage?: number | null;
  routeSection?: string | null;
  passage?: PassageResponse;
  selectedText?: string | null;
}): PassageVerification {
  const mismatchReasons: string[] = [];
  const routeVerified = Boolean(args.passage && args.passage.document_id === args.documentId);

  let versionMatched: boolean | null = null;
  if (args.routeVersion) {
    versionMatched = args.passage ? args.passage.version_hash === args.routeVersion : null;
    if (versionMatched === false) {
      mismatchReasons.push("Version hash does not match the URL version.");
    }
  }

  let pageMatched: boolean | null = null;
  if (args.routePage !== null && args.routePage !== undefined) {
    pageMatched = args.passage ? args.passage.page_number === args.routePage : null;
    if (pageMatched === false) {
      mismatchReasons.push("Page number does not match the URL page.");
    }
  }

  let sectionMatched: boolean | null = null;
  if (args.routeSection) {
    sectionMatched = args.passage ? args.passage.section_id === args.routeSection : null;
    if (sectionMatched === false) {
      mismatchReasons.push("Section id does not match the URL section.");
    }
  }

  let textMatched: boolean | null = null;
  if (args.selectedText) {
    textMatched = args.passage
      ? normalizeDocumentText(args.passage.text) === normalizeDocumentText(args.selectedText)
      : null;
    if (textMatched === false) {
      mismatchReasons.push("Exact passage text does not match the selected evidence context.");
    }
  }

  const label = !args.passage
    ? "Passage not loaded"
    : mismatchReasons.length > 0
      ? "Passage loaded with mismatches"
      : routeVerified
        ? "Route and version verified"
        : "Passage loaded";

  return {
    routeVerified,
    versionMatched,
    pageMatched,
    sectionMatched,
    textMatched,
    mismatchReasons,
    label,
  };
}

function setQueryValue(searchParams: URLSearchParams, key: string, value: string | number | null | undefined): void {
  if (value === null || value === undefined || value === "") {
    searchParams.delete(key);
    return;
  }
  searchParams.set(key, String(value));
}

function buildDocumentHref(pathname: string, searchParams: URLSearchParams): string {
  const query = searchParams.toString();
  return query ? `${pathname}?${query}` : pathname;
}

function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(720);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }

    const update = () => {
      const nextWidth = Math.floor(element.getBoundingClientRect().width);
      if (nextWidth > 0) {
        setWidth(nextWidth);
      }
    };

    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function PageIndexInput({
  page,
  onChange,
  pageCount,
}: {
  page: number;
  onChange: (page: number) => void;
  pageCount: number | null;
}) {
  const [draft, setDraft] = useState(String(page));

  useEffect(() => {
    setDraft(String(page));
  }, [page]);

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const nextPage = Number.parseInt(draft, 10);
        if (!Number.isFinite(nextPage) || nextPage < 1) {
          setDraft(String(page));
          return;
        }
        if (pageCount && nextPage > pageCount) {
          setDraft(String(page));
          return;
        }
        onChange(nextPage);
      }}
    >
      <label className="sr-only" htmlFor="document-page-input">
        Page number
      </label>
      <input
        id="document-page-input"
        inputMode="numeric"
        pattern="[0-9]*"
        value={draft}
        onChange={(event) => setDraft(event.currentTarget.value)}
        className="h-7 w-16 rounded-md border border-border bg-background px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
      />
      <Button type="submit" size="sm" variant="outline">
        Go
      </Button>
    </form>
  );
}

function PdfViewer({
  objectUrl,
  page,
  passage,
  onPageChange,
}: {
  objectUrl: string;
  page: number;
  passage?: PassageResponse;
  onPageChange: (page: number) => void;
}) {
  const [runtime, setRuntime] = useState<PdfRuntime | null>(null);
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [textMatch, setTextMatch] = useState<boolean | null>(null);
  const [viewerRef, width] = useElementWidth<HTMLDivElement>();

  useEffect(() => {
    let active = true;
    void import("react-pdf")
      .then((module) => {
        module.pdfjs.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC;
        if (active) {
          setRuntime(module as unknown as PdfRuntime);
        }
      })
      .catch(() => {
        if (active) {
          setRuntime(null);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    setPageCount(null);
    setTextMatch(null);
  }, [objectUrl]);

  if (!runtime) {
    return (
      <div className="flex min-h-[540px] items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 p-8 text-sm text-muted-foreground">
        Loading PDF viewer...
      </div>
    );
  }

  const PdfDocument = runtime.Document as ComponentType<Record<string, unknown>>;
  const PdfPage = runtime.Page as ComponentType<Record<string, unknown>>;
  const hasExactTextTarget = Boolean(passage?.text);
  const resolvedWidth = Math.max(360, width - 24);
  const currentPage = Math.max(1, page);
  const canGoPrevious = currentPage > 1;
  const canGoNext = pageCount ? currentPage < pageCount : true;

  return (
    <div ref={viewerRef} className="flex min-h-[540px] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-5">
            PDF
          </Badge>
          <span aria-live="polite">
            {pageCount ? `Page ${currentPage} of ${pageCount}` : `Page ${currentPage}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {hasExactTextTarget ? (
            <Badge variant={textMatch ? "secondary" : "outline"} className="h-5">
              {textMatch ? "Exact text layer match" : "Exact highlight not guaranteed"}
            </Badge>
          ) : (
            <Badge variant="outline" className="h-5">
              Page targeted
            </Badge>
          )}
          <PageIndexInput page={currentPage} onChange={onPageChange} pageCount={pageCount} />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!canGoPrevious}
        >
          <ArrowLeftIcon className="size-4" />
          Previous
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!canGoNext}
        >
          Next
          <ArrowRightIcon className="size-4" />
        </Button>
      </div>

      <div className="overflow-auto rounded-lg border border-border bg-white/80 p-3">
        <PdfDocument
          file={objectUrl}
          loading={<div className="p-4 text-sm text-muted-foreground">Loading PDF artifact...</div>}
          onLoadSuccess={({ numPages }: { numPages: number }) => setPageCount(numPages)}
          onLoadError={() => setPageCount(null)}
        >
          <PdfPage
            pageNumber={Math.min(currentPage, pageCount ?? currentPage)}
            width={resolvedWidth}
            renderTextLayer
            renderAnnotationLayer={false}
            onGetTextSuccess={(textContent: { items?: Array<{ str?: string }> }) => {
              if (!passage?.text) {
                setTextMatch(null);
                return;
              }
              const joinedText = (textContent.items ?? []).map((item) => item.str ?? "").join(" ");
              setTextMatch(
                normalizeDocumentText(joinedText).includes(normalizeDocumentText(passage.text)),
              );
            }}
            customTextRenderer={
              hasExactTextTarget
                ? ({ str }: { str: string }) => {
                    if (normalizeDocumentText(str) === normalizeDocumentText(passage?.text ?? "")) {
                      return `<mark class="rounded bg-amber-200/70 px-0.5 text-inherit">${escapeHtml(
                        str,
                      )}</mark>`;
                    }
                    return escapeHtml(str);
                  }
                : undefined
            }
          />
        </PdfDocument>
      </div>
    </div>
  );
}

function HtmlViewer({
  objectUrl,
  artifact,
  onDownloadArtifact,
}: {
  objectUrl: string;
  artifact: DocumentArtifact;
  onDownloadArtifact: () => void;
}) {
  return (
    <div className="flex min-h-[540px] flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-5">
            HTML
          </Badge>
          <span>Isolated sandbox preview</span>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onDownloadArtifact}>
          <DownloadIcon className="size-4" />
          Download source
        </Button>
      </div>
      <iframe
        title={`HTML source preview for ${artifact.artifact_id}`}
        src={objectUrl}
        sandbox=""
        className="min-h-[540px] w-full rounded-lg border border-border bg-white"
      />
    </div>
  );
}

function ArtifactFallback({
  artifact,
  onDownloadArtifact,
}: {
  artifact?: DocumentArtifact;
  onDownloadArtifact: () => void;
}) {
  return (
    <div className="flex min-h-[540px] flex-col justify-between rounded-lg border border-dashed border-border bg-muted/25 p-4">
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <AlertCircleIcon className="size-4 text-muted-foreground" />
          Source viewer unavailable
        </div>
        <p className="text-sm text-muted-foreground">
          {artifact
            ? "The selected artifact could not be rendered inline. Use the download action or open the FDA source link."
            : "No preserved artifact is available for this guidance document."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onDownloadArtifact}>
          <DownloadIcon className="size-4" />
          Download source
        </Button>
      </div>
    </div>
  );
}

function SourceViewer({
  artifact,
  artifactResource,
  passage,
  page,
  onPageChange,
  onDownloadArtifact,
}: {
  artifact?: DocumentArtifact;
  artifactResource: AuthenticatedBlobResource | null | undefined;
  passage?: PassageResponse;
  page: number;
  onPageChange: (page: number) => void;
  onDownloadArtifact: () => void;
}) {
  if (!artifact || !artifactResource) {
    return <ArtifactFallback artifact={artifact} onDownloadArtifact={onDownloadArtifact} />;
  }

  const contentType = safeLower(artifactResource.contentType || artifact.content_type);
  if (contentType.includes("pdf")) {
    return (
      <PdfViewer
        objectUrl={artifactResource.objectUrl}
        page={page}
        passage={passage}
        onPageChange={onPageChange}
      />
    );
  }

  if (contentType.includes("html")) {
    return <HtmlViewer objectUrl={artifactResource.objectUrl} artifact={artifact} onDownloadArtifact={onDownloadArtifact} />;
  }

  return <ArtifactFallback artifact={artifact} onDownloadArtifact={onDownloadArtifact} />;
}

function MetaRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-border bg-background/70 px-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right text-foreground">{value}</span>
    </div>
  );
}

function InspectorSection({
  metadata,
  passage,
  verification,
  selectedSection,
  selectedVersion,
  selectedArtifact,
  onDownloadArtifact,
}: {
  metadata: DocumentMetadata;
  passage?: PassageResponse;
  verification?: PassageVerification;
  selectedSection?: SectionNavigationEntry;
  selectedVersion?: string | null;
  selectedArtifact?: DocumentArtifact;
  onDownloadArtifact: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium text-foreground">Passage inspector</p>
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {verification?.label ?? "Awaiting passage selection"}
            </p>
          </div>
          <Badge
            variant={verification?.mismatchReasons.length ? "destructive" : "secondary"}
            className="h-5"
          >
            {verification?.routeVerified ? "Verified" : "Inspect"}
          </Badge>
        </div>

        <div className="space-y-2">
          <MetaRow label="Document" value={metadata.document_id} />
          <MetaRow label="Status" value={formatStatus(metadata.status)} />
          <MetaRow label="Version" value={selectedVersion ?? metadata.version_hash} />
          <MetaRow label="Section" value={selectedSection?.section_title ?? passage?.section_title ?? selectedSection?.section_id ?? passage?.section_id ?? "-"} />
          <MetaRow label="Page" value={passage?.page_number ?? selectedSection?.page_number ?? "-"} />
          <MetaRow label="Source" value={<Link className="text-primary underline-offset-4 hover:underline" href={metadata.source_url} target="_blank" rel="noreferrer">FDA source</Link>} />
        </div>

        {verification?.mismatchReasons.length ? (
          <div className="mt-3 space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            {verification.mismatchReasons.map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
          </div>
        ) : null}
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-foreground">Exact passage</p>
          {selectedArtifact ? (
            <Button type="button" variant="outline" size="sm" onClick={onDownloadArtifact}>
              <DownloadIcon className="size-4" />
              Download source
            </Button>
          ) : null}
        </div>
        <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
          {passage?.text ?? "Select a citation target to load the exact passage."}
        </p>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-3">
        <p className="mb-2 text-sm font-medium text-foreground">Document details</p>
        <div className="space-y-2 text-sm">
          <MetaRow label="Title" value={metadata.title} />
          <MetaRow label="FDA center" value={metadata.center ?? metadata.issuing_office ?? "-"} />
          <MetaRow label="Issued" value={formatDate(metadata.issue_date ?? metadata.published_date)} />
          <MetaRow label="Last changed" value={formatDate(metadata.fda_last_changed)} />
          <MetaRow label="Retrieved" value={formatDate(metadata.retrieved_at)} />
          <MetaRow label="Docket" value={metadata.docket_number ?? "-"} />
        </div>
      </div>
    </div>
  );
}

function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const variant = status === "Withdrawn" ? "destructive" : status === "Draft" ? "outline" : "secondary";
  return (
    <Badge variant={variant} className="h-6">
      {status}
    </Badge>
  );
}

export function DocumentWorkspaceView({
  documentId,
  metadata,
  sections,
  versions,
  artifacts,
  routeState,
  passage,
  passageVerification,
  artifactResource,
  artifactError,
  selectedArtifactId,
  selectedSectionId,
  onSelectArtifact,
  onNavigatePage,
  onNavigateSection,
  onNavigateVersion,
  onDownloadArtifact,
  onOpenArtifact,
  summaryType,
  onSummaryTypeChange,
  summarySectionRef,
  onSummaryCreated,
}: DocumentWorkspaceViewProps) {
  const selectedArtifact = artifacts.find((artifact) => artifact.artifact_id === selectedArtifactId);
  const effectiveArtifact = selectedArtifact ?? selectPreferredArtifact(artifacts);
  const activeSection = sections.find((section) => section.section_id === selectedSectionId);
  const currentPage = routeState.page ?? passage?.page_number ?? activeSection?.page_number ?? 1;
  const inspectorArtifact = effectiveArtifact;

  return (
    <div className="space-y-3">
      <header className="space-y-3 rounded-lg border border-border bg-surface-raised p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">{metadata.title}</h1>
              <DocumentStatusBadge status={metadata.status} />
              <Badge variant="outline" className="h-6">
                Version {routeState.version ?? metadata.version_hash.slice(0, 12)}
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{metadata.center ?? metadata.issuing_office ?? "FDA guidance"}</span>
              <span>•</span>
              <Link className="text-primary underline-offset-4 hover:underline" href={metadata.source_url} target="_blank" rel="noreferrer">
                FDA source
              </Link>
              <span>•</span>
              <span>{documentId}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onOpenArtifact} disabled={!inspectorArtifact}>
              <PanelRightIcon className="size-4" />
              Open artifact
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onDownloadArtifact} disabled={!inspectorArtifact}>
              <DownloadIcon className="size-4" />
              Download
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onSummaryTypeChange("summary");
                summarySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              <FileTextIcon className="size-4" />
              Summary
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onSummaryTypeChange("key_changes");
                summarySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              <Layers3Icon className="size-4" />
              Key changes
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onSummaryTypeChange("key_requirements");
                summarySectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
            >
              <FileTextIcon className="size-4" />
              Key requirements
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {versions.map((version) => (
            <Button
              key={version.version_hash}
              type="button"
              variant={version.version_hash === (routeState.version ?? metadata.version_hash) ? "secondary" : "outline"}
              size="sm"
              onClick={() => onNavigateVersion(version.version_hash)}
            >
              {version.version_hash.slice(0, 12)}
            </Button>
          ))}
          {artifacts.map((artifact) => (
            <Button
              key={artifact.artifact_id}
              type="button"
              variant={artifact.artifact_id === effectiveArtifact?.artifact_id ? "secondary" : "outline"}
              size="sm"
              onClick={() => onSelectArtifact(artifact.artifact_id)}
            >
              {safeLower(artifact.content_type).includes("pdf") ? "PDF" : safeLower(artifact.content_type).includes("html") ? "HTML" : artifact.artifact_kind}
            </Button>
          ))}
        </div>
      </header>

      {artifactError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive" role="alert">
          {artifactError}
        </div>
      ) : null}

      <div className="hidden md:block">
        <ResizablePanelGroup className="min-h-[760px] rounded-lg border border-border bg-background/60">
          <ResizablePanel defaultSize={20} minSize={16} maxSize={28} className="min-w-0">
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-3 py-2 text-sm font-medium text-foreground">
                <span>Sections</span>
                <Badge variant="outline" className="h-5">
                  {sections.length}
                </Badge>
              </div>
              <ScrollArea className="h-full">
                <div className="space-y-1 p-3">
                  {sections.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No section map is available.</p>
                  ) : (
                    sections.map((section) => {
                      const active = section.section_id === activeSection?.section_id;
                      return (
                        <button
                          key={section.section_id}
                          type="button"
                          className={cn(
                            "flex w-full flex-col items-start gap-1 rounded-lg border px-3 py-2 text-left text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring",
                            active
                              ? "border-primary/40 bg-primary/10 text-foreground"
                              : "border-border bg-background/70 hover:bg-muted/60",
                          )}
                          onClick={() => onNavigateSection(section)}
                        >
                          <span className="font-medium">{section.section_title ?? section.section_id}</span>
                          <span className="text-xs text-muted-foreground">
                            {section.page_number ? `Page ${section.page_number}` : "Page not mapped"}
                          </span>
                        </button>
                      );
                    })
                  )}
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          <ResizablePanel defaultSize={48} minSize={34} className="min-w-0">
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-3 py-2 text-sm font-medium text-foreground">
                <span>Source viewer</span>
                <div className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
                  {passageVerification?.label ?? "Waiting for source"}
                </div>
              </div>
              <div className="flex-1 p-3">
                <SourceViewer
                  artifact={inspectorArtifact}
                  artifactResource={artifactResource}
                  passage={passage}
                  page={currentPage}
                  onPageChange={onNavigatePage}
                  onDownloadArtifact={onDownloadArtifact}
                />
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          <ResizablePanel defaultSize={32} minSize={24} className="min-w-0">
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between border-b border-border px-3 py-2 text-sm font-medium text-foreground">
                <span>Passage inspector</span>
                {passageVerification?.routeVerified ? (
                  <Badge variant={passageVerification.mismatchReasons.length ? "destructive" : "secondary"} className="h-5">
                    {passageVerification.mismatchReasons.length ? "Needs review" : "Verified"}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="h-5">
                    Inspect
                  </Badge>
                )}
              </div>
              <ScrollArea className="flex-1">
                <div className="p-3">
                  <InspectorSection
                    metadata={metadata}
                    passage={passage}
                    verification={passageVerification}
                    selectedSection={activeSection}
                    selectedVersion={routeState.version}
                    selectedArtifact={inspectorArtifact}
                    onDownloadArtifact={onDownloadArtifact}
                  />
                </div>
              </ScrollArea>
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      <div className="space-y-3 md:hidden">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-background p-2">
          <Sheet>
            <SheetTrigger render={<Button variant="outline" size="sm" />}>
              <MenuIcon className="size-4" />
              Sections
            </SheetTrigger>
            <SheetContent side="left" className="w-[92vw] max-w-sm p-0">
              <SheetHeader className="border-b border-border p-4">
                <SheetTitle>Sections</SheetTitle>
              </SheetHeader>
              <ScrollArea className="h-full p-3">
                <div className="space-y-1">
                  {sections.map((section) => (
                    <button
                      key={section.section_id}
                      type="button"
                      className="flex w-full flex-col items-start gap-1 rounded-lg border border-border bg-background px-3 py-2 text-left text-sm"
                      onClick={() => onNavigateSection(section)}
                    >
                      <span className="font-medium">{section.section_title ?? section.section_id}</span>
                      <span className="text-xs text-muted-foreground">
                        {section.page_number ? `Page ${section.page_number}` : "Page not mapped"}
                      </span>
                    </button>
                  ))}
                </div>
              </ScrollArea>
            </SheetContent>
          </Sheet>

          <Sheet>
            <SheetTrigger render={<Button variant="outline" size="sm" />}>
              <PanelLeftIcon className="size-4" />
              Inspector
            </SheetTrigger>
            <SheetContent side="right" className="w-[92vw] max-w-md p-0">
              <SheetHeader className="border-b border-border p-4">
                <SheetTitle>Passage inspector</SheetTitle>
              </SheetHeader>
              <ScrollArea className="h-full p-3">
                <InspectorSection
                  metadata={metadata}
                  passage={passage}
                  verification={passageVerification}
                  selectedSection={activeSection}
                  selectedVersion={routeState.version}
                  selectedArtifact={inspectorArtifact}
                  onDownloadArtifact={onDownloadArtifact}
                />
              </ScrollArea>
            </SheetContent>
          </Sheet>

          <Badge variant={passageVerification?.mismatchReasons.length ? "destructive" : "secondary"} className="h-6">
            {passageVerification?.label ?? "Ready"}
          </Badge>
        </div>

        <div className="rounded-lg border border-border bg-background/60 p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium text-foreground">Source viewer</p>
              <p className="text-xs text-muted-foreground">{passageVerification?.label ?? "Waiting for source"}</p>
            </div>
            <PageIndexInput page={currentPage} onChange={onNavigatePage} pageCount={null} />
          </div>
          <SourceViewer
            artifact={inspectorArtifact}
            artifactResource={artifactResource}
            passage={passage}
            page={currentPage}
            onPageChange={onNavigatePage}
            onDownloadArtifact={onDownloadArtifact}
          />
        </div>
      </div>

      <section id="summary" ref={summarySectionRef}>
        <SummaryGenerationPanel
          documentId={documentId}
          currentVersionHash={routeState.version ?? metadata.version_hash}
          versions={versions}
          summaryType={summaryType}
          onSummaryTypeChange={onSummaryTypeChange}
          onSummaryCreated={onSummaryCreated}
        />
      </section>
    </div>
  );
}

export default function DocumentWorkspace({ documentId }: { documentId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const apiClient = useMemo(() => createApiClient(), []);
  const initialSummaryType = useMemo<SummaryType>(() => {
    const summary = searchParams.get("summary");
    if (summary === "key_requirements" || summary === "key_changes" || summary === "summary") {
      return summary;
    }
    return "summary";
  }, [searchParams]);
  const [summaryType, setSummaryType] = useState<SummaryType>(initialSummaryType);
  const summarySectionRef = useRef<HTMLElement | null>(null);
  const routeState = useMemo(() => {
    const pageParam = searchParams.get("page");
    const version = searchParams.get("version");
    const chunkId = searchParams.get("chunk") ?? undefined;
    const section = searchParams.get("section") ?? undefined;
    const page = pageParam ? Number.parseInt(pageParam, 10) : null;

    return {
      chunkId,
      page: Number.isFinite(page ?? Number.NaN) ? page : null,
      version,
      section,
    };
  }, [searchParams]);

  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => apiClient.getDocument(documentId),
  });

  const sectionsQuery = useQuery({
    queryKey: ["document-sections", documentId],
    queryFn: () => apiClient.getSections(documentId),
  });

  const passageQuery = useQuery({
    queryKey: ["document-passage", documentId, routeState.chunkId],
    queryFn: () => apiClient.getPassage(documentId, routeState.chunkId ?? ""),
    enabled: Boolean(routeState.chunkId),
  });

  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [artifactResource, setArtifactResource] = useState<AuthenticatedBlobResource | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const artifactResourceRef = useRef<AuthenticatedBlobResource | null>(null);

  const metadata = documentQuery.data?.metadata;
  const sections = sectionsQuery.data ?? [];
  const passage = passageQuery.data;
  const versions = useMemo(() => documentQuery.data?.versions ?? [], [documentQuery.data?.versions]);
  const artifacts = useMemo(() => documentQuery.data?.artifacts ?? [], [documentQuery.data?.artifacts]);
  const preferredArtifact = selectPreferredArtifact(artifacts);
  const selectedArtifact = artifacts.find((artifact) => artifact.artifact_id === selectedArtifactId) ?? preferredArtifact;
  const selectedSectionId = routeState.section ?? passage?.section_id ?? sections[0]?.section_id ?? null;

  useEffect(() => {
    if (!routeState.chunkId || !passage) {
      return;
    }

    const nextSearchParams = new URLSearchParams(searchParams.toString());
    let changed = false;

    if (!nextSearchParams.get("page") && passage.page_number !== null && passage.page_number !== undefined) {
      setQueryValue(nextSearchParams, "page", passage.page_number);
      changed = true;
    }
    if (!nextSearchParams.get("section") && passage.section_id) {
      setQueryValue(nextSearchParams, "section", passage.section_id);
      changed = true;
    }
    if (!nextSearchParams.get("version") && passage.version_hash) {
      setQueryValue(nextSearchParams, "version", passage.version_hash);
      changed = true;
    }

    if (changed) {
      router.replace(buildDocumentHref(pathname, nextSearchParams), { scroll: false });
    }
  }, [passage, pathname, router, routeState.chunkId, searchParams]);

  useEffect(() => {
    setSummaryType(initialSummaryType);
  }, [initialSummaryType]);

  useEffect(() => {
    if (!preferredArtifact) {
      setSelectedArtifactId(null);
      return;
    }
    setSelectedArtifactId((current) => (current && artifacts.some((artifact) => artifact.artifact_id === current) ? current : preferredArtifact.artifact_id));
  }, [artifacts, preferredArtifact]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    if (!selectedArtifact) {
      setArtifactResource(null);
      setArtifactError(null);
      return () => controller.abort();
    }

    setArtifactError(null);
    void createAuthenticatedBlobResource({
      apiClient,
      documentId,
      artifactId: selectedArtifact.artifact_id,
      signal: controller.signal,
    })
      .then((resource) => {
        if (!active) {
          resource.revoke();
          return;
        }
        setArtifactResource((current) => {
          current?.revoke();
          artifactResourceRef.current = resource;
          return resource;
        });
      })
      .catch((error: unknown) => {
        if (!active || controller.signal.aborted) {
          return;
        }
        setArtifactResource(null);
        setArtifactError(error instanceof Error ? error.message : "Failed to load the selected artifact.");
      });

    return () => {
      active = false;
      controller.abort();
      artifactResourceRef.current?.revoke();
      artifactResourceRef.current = null;
    };
  }, [apiClient, documentId, selectedArtifact]);

  const passageVerification = useMemo(
    () =>
      verifyPassageTarget({
        documentId,
        routeVersion: routeState.version,
        routePage: routeState.page,
        routeSection: routeState.section,
        passage,
      }),
    [documentId, passage, routeState.page, routeState.section, routeState.version],
  );

  const handleNavigatePage = (page: number) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString());
    setQueryValue(nextSearchParams, "page", page);
    router.replace(buildDocumentHref(pathname, nextSearchParams), { scroll: false });
  };

  const handleNavigateSection = (section: SectionNavigationEntry) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString());
    setQueryValue(nextSearchParams, "section", section.section_id);
    if (section.page_number !== null && section.page_number !== undefined) {
      setQueryValue(nextSearchParams, "page", section.page_number);
    }
    router.replace(buildDocumentHref(pathname, nextSearchParams), { scroll: false });
  };

  const handleNavigateVersion = (versionHash: string) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString());
    setQueryValue(nextSearchParams, "version", versionHash);
    router.replace(buildDocumentHref(pathname, nextSearchParams), { scroll: false });
  };

  const handleDownloadArtifact = () => {
    if (!selectedArtifact) {
      return;
    }
    void downloadArtifactWithAuth({
      apiClient,
      documentId,
      artifactId: selectedArtifact.artifact_id,
    });
  };

  const handleOpenArtifact = () => {
    if (!selectedArtifact) {
      return;
    }
    const current = artifactResource;
    if (!current) {
      handleDownloadArtifact();
      return;
    }
    window.open(current.objectUrl, "_blank", "noopener,noreferrer");
  };

  const handleSummaryCreated = (summaryId: string) => {
    router.push(`/summaries/${encodeURIComponent(summaryId)}`);
  };

  if (documentQuery.isLoading || sectionsQuery.isLoading || !metadata) {
    return (
      <div className="space-y-3">
        <div className="rounded-lg border border-border bg-surface-raised p-4">
          <Skeleton className="h-8 w-2/3" />
          <div className="mt-3 flex gap-2">
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-28" />
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <Skeleton className="h-[760px] rounded-lg" />
          <Skeleton className="h-[760px] rounded-lg md:col-span-2" />
        </div>
      </div>
    );
  }

  if (documentQuery.isError || sectionsQuery.isError) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive" role="alert">
        Failed to load the document viewer.
      </div>
    );
  }

  return (
    <DocumentWorkspaceView
      documentId={documentId}
      metadata={metadata}
      sections={sections}
      versions={versions}
      artifacts={artifacts}
      routeState={routeState}
      passage={passage}
      passageVerification={passageVerification}
      artifactResource={artifactResource}
      artifactError={artifactError}
      selectedArtifactId={selectedArtifact?.artifact_id ?? null}
      selectedSectionId={selectedSectionId}
      onSelectArtifact={setSelectedArtifactId}
      onNavigatePage={handleNavigatePage}
      onNavigateSection={handleNavigateSection}
      onNavigateVersion={handleNavigateVersion}
      onDownloadArtifact={handleDownloadArtifact}
      onOpenArtifact={handleOpenArtifact}
      summaryType={summaryType}
      onSummaryTypeChange={setSummaryType}
      summarySectionRef={summarySectionRef}
      onSummaryCreated={handleSummaryCreated}
    />
  );
}