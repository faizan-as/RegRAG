"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircleIcon,
  FilterIcon,
  Loader2Icon,
  SearchIcon,
  SlidersHorizontalIcon,
  UnplugIcon,
} from "lucide-react";
import type { components } from "@/lib/api/schema";
import { useSearchQuery } from "@/hooks/use-search-query";
import {
  buildSearchRequest,
  emptySearchFormValues,
  parseSearchState,
  serializeSearchState,
  type SearchFormValues,
} from "@/lib/search/filters";
import { isApiClientError } from "@/lib/api/errors";
import { EvidenceCard } from "@/components/citations/evidence-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

type SearchResponse = components["schemas"]["SearchResponse"];
type SearchResult = components["schemas"]["SearchResult"];
type Evidence = components["schemas"]["EvidenceCard"];

function scoreLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return value.toFixed(4);
}

function summarizePartialFallback(diagnostics: Record<string, unknown> | undefined): string | null {
  if (!diagnostics) {
    return null;
  }

  const denseStatus = String(
    diagnostics.dense_status ??
      (diagnostics.dense as { status?: unknown } | undefined)?.status ??
      "",
  ).toLowerCase();
  const keywordStatus = String(
    diagnostics.keyword_status ??
      (diagnostics.keyword as { status?: unknown } | undefined)?.status ??
      "",
  ).toLowerCase();

  const denseDown = denseStatus.includes("fail") || denseStatus.includes("error") || denseStatus.includes("down");
  const keywordDown =
    keywordStatus.includes("fail") || keywordStatus.includes("error") || keywordStatus.includes("down");

  if (denseDown && keywordDown) {
    return "Dense and keyword retrieval both reported degraded status.";
  }
  if (denseDown) {
    return "Dense retrieval reported degraded status; keyword retrieval fallback may be partial.";
  }
  if (keywordDown) {
    return "Keyword retrieval reported degraded status; dense retrieval fallback may be partial.";
  }

  return null;
}

function SearchFiltersForm({
  values,
  onChange,
}: {
  values: SearchFormValues;
  onChange: (next: SearchFormValues) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
      <Input
        aria-label="FDA center"
        placeholder="Center"
        value={values.center}
        onChange={(event) => onChange({ ...values, center: event.currentTarget.value })}
      />

      <Input
        aria-label="Topics"
        placeholder="Topics (comma separated)"
        value={values.topics}
        onChange={(event) => onChange({ ...values, topics: event.currentTarget.value })}
      />

      <Select
        value={values.status || "any"}
        onValueChange={(status) =>
          onChange({ ...values, status: !status || status === "any" ? "" : status })
        }
      >
        <SelectTrigger aria-label="Guidance status" className="w-full">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="any">Any status</SelectItem>
          <SelectItem value="Draft">Draft</SelectItem>
          <SelectItem value="Final">Final</SelectItem>
          <SelectItem value="Withdrawn">Withdrawn</SelectItem>
        </SelectContent>
      </Select>

      <Input
        aria-label="Docket ID"
        placeholder="Docket ID"
        value={values.docketId}
        onChange={(event) => onChange({ ...values, docketId: event.currentTarget.value })}
      />

      <Input
        type="date"
        aria-label="Issue date from"
        value={values.dateFrom}
        onChange={(event) => onChange({ ...values, dateFrom: event.currentTarget.value })}
      />

      <Input
        type="date"
        aria-label="Issue date to"
        value={values.dateTo}
        onChange={(event) => onChange({ ...values, dateTo: event.currentTarget.value })}
      />

      <Input
        aria-label="CFR references"
        placeholder="CFR (comma separated)"
        value={values.cfr}
        onChange={(event) => onChange({ ...values, cfr: event.currentTarget.value })}
      />

      <Input
        aria-label="Product code"
        placeholder="Product code (comma separated)"
        value={values.productCode}
        onChange={(event) => onChange({ ...values, productCode: event.currentTarget.value })}
      />
    </div>
  );
}

function buildEvidenceMap(payload: SearchResponse | undefined): Map<string, Evidence> {
  const map = new Map<string, Evidence>();
  for (const evidence of payload?.evidence ?? []) {
    map.set(evidence.chunk_id, evidence);
  }
  return map;
}

function SearchRows({
  results,
  evidenceMap,
  onSelect,
  selectedChunkId,
}: {
  results: SearchResult[];
  evidenceMap: Map<string, Evidence>;
  onSelect: (chunkId: string) => void;
  selectedChunkId: string | null;
}) {
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[920px]">
        <div className="grid h-8 grid-cols-[2.2fr_3.4fr_1.5fr_0.9fr_0.9fr] items-center border-b border-border px-2 text-xs font-medium text-muted-foreground">
          <span>Document</span>
          <span>Passage</span>
          <span>Section / page</span>
          <span>Status</span>
          <span>Rank / rerank</span>
        </div>
        {results.map((result) => {
          const evidence = evidenceMap.get(result.chunk.chunk_id);
          const isSelected = selectedChunkId === result.chunk.chunk_id;
          return (
            <button
              type="button"
              key={result.chunk.chunk_id}
              className="grid w-full grid-cols-[2.2fr_3.4fr_1.5fr_0.9fr_0.9fr] items-start gap-2 border-b border-border px-2 py-2 text-left text-xs hover:bg-muted/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary"
              onClick={() => onSelect(result.chunk.chunk_id)}
              aria-pressed={isSelected}
            >
              <span className="line-clamp-2 text-foreground">{evidence?.title ?? result.chunk.document_id}</span>
              <span className="line-clamp-3 text-muted-foreground">{evidence?.passage ?? result.chunk.text}</span>
              <span className="text-muted-foreground">
                {result.chunk.section_title || result.chunk.section_id || "-"}
                <br />
                page {result.chunk.page_number ?? "-"}
              </span>
              <span>{evidence?.document_status ?? "-"}</span>
              <span>
                {(result.rank ?? "-").toString()} / {scoreLabel(result.rerank_score)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="grid grid-cols-[2.2fr_3.4fr_1.5fr_0.9fr_0.9fr] gap-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ))}
    </div>
  );
}

function ErrorNotice({ error }: { error: unknown }) {
  if (!isApiClientError(error)) {
    return (
      <Alert variant="destructive">
        <AlertCircleIcon />
        <AlertTitle>Search failed</AlertTitle>
        <AlertDescription>The service could not complete this request.</AlertDescription>
      </Alert>
    );
  }

  if (error.isCanceled) {
    return (
      <Alert>
        <UnplugIcon />
        <AlertTitle>Search canceled</AlertTitle>
        <AlertDescription>The request was canceled before completion.</AlertDescription>
      </Alert>
    );
  }

  if (error.category === "validation") {
    return (
      <Alert>
        <AlertCircleIcon />
        <AlertTitle>Validation needed</AlertTitle>
        <AlertDescription>Review your query or filters and submit again.</AlertDescription>
      </Alert>
    );
  }

  if (error.category === "rate_limited") {
    const retryText = error.retryAfter?.seconds
      ? ` Retry after about ${error.retryAfter.seconds} seconds.`
      : " Retry after the interval provided by the service.";
    return (
      <Alert>
        <AlertCircleIcon />
        <AlertTitle>Rate limit reached</AlertTitle>
        <AlertDescription>{`Too many requests were sent.${retryText}`}</AlertDescription>
      </Alert>
    );
  }

  if (error.category === "unavailable") {
    return (
      <Alert>
        <UnplugIcon />
        <AlertTitle>Service unavailable</AlertTitle>
        <AlertDescription>The retrieval service is temporarily unavailable. Try again shortly.</AlertDescription>
      </Alert>
    );
  }

  return (
    <Alert variant="destructive">
      <AlertCircleIcon />
      <AlertTitle>Search failed</AlertTitle>
      <AlertDescription>Request could not be completed. Check access and try again.</AlertDescription>
    </Alert>
  );
}

export function SearchWorkspace({ resource }: { resource: "research" | "search" }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const parsedState = useMemo(() => parseSearchState(searchParams), [searchParams]);
  const [draftValues, setDraftValues] = useState<SearchFormValues>(parsedState.values);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);

  useEffect(() => {
    setDraftValues(parsedState.values);
  }, [parsedState.values]);

  const request = useMemo(
    () => buildSearchRequest(parsedState.values, parsedState.passthroughFilters),
    [parsedState],
  );

  const query = useSearchQuery({
    request,
    resource,
    enabled: parsedState.submitted && request.query.trim().length > 0,
  });

  const evidenceMap = useMemo(() => buildEvidenceMap(query.data), [query.data]);

  useEffect(() => {
    const firstChunkId = query.data?.results?.[0]?.chunk.chunk_id ?? null;
    setSelectedChunkId(firstChunkId);
  }, [query.data]);

  const selectedEvidence = selectedChunkId ? evidenceMap.get(selectedChunkId) : undefined;
  const ignoredFilterKeys = query.data?.transparency?.ignored_filter_keys ?? [];
  const diagnostics = query.data?.transparency?.retrieval_diagnostics as
    | Record<string, unknown>
    | undefined;
  const fallbackNotice = summarizePartialFallback(diagnostics);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const params = serializeSearchState(
      draftValues,
      true,
      parsedState.passthroughFilters,
    );
    router.push(params.toString() ? `${pathname}?${params.toString()}` : pathname);
  };

  const onReset = () => {
    const next = emptySearchFormValues();
    setDraftValues(next);
    router.push(pathname);
  };

  const results = query.data?.results ?? [];

  return (
    <section className="space-y-3 rounded-lg border border-border bg-card p-3 sm:p-4">
      <header className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-lg font-semibold">Search workspace</h1>
          <Badge variant="secondary" className="h-6">Citation-first</Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          Submit a query to retrieve evidence-backed FDA passages with diagnostics.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-2">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <SearchIcon className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
            <Input
              className="pl-8"
              value={draftValues.query}
              onChange={(event) => setDraftValues({ ...draftValues, query: event.currentTarget.value })}
              placeholder="Search FDA guidance and evidence passages"
              aria-label="Search query"
            />
          </div>

          <div className="flex gap-2">
            <Sheet>
              <SheetTrigger render={<Button type="button" variant="outline" className="md:hidden" />}>
                <FilterIcon className="size-4" />
                Filters
              </SheetTrigger>
              <SheetContent side="bottom" className="max-h-[85svh] overflow-auto">
                <SheetHeader>
                  <SheetTitle>Search filters</SheetTitle>
                </SheetHeader>
                <div className="px-4 pb-4">
                  <SearchFiltersForm values={draftValues} onChange={setDraftValues} />
                </div>
              </SheetContent>
            </Sheet>

            <Button type="submit" className="min-w-20" disabled={!draftValues.query.trim() || query.isFetching}>
              {query.isFetching ? <Loader2Icon className="size-4 animate-spin" /> : null}
              Submit
            </Button>
            <Button type="button" variant="outline" onClick={onReset}>
              Reset
            </Button>
          </div>
        </div>

        <div className="hidden md:block">
          <SearchFiltersForm values={draftValues} onChange={setDraftValues} />
        </div>
      </form>

      {!parsedState.submitted ? (
        <Alert>
          <SlidersHorizontalIcon />
          <AlertTitle>Ready to search</AlertTitle>
          <AlertDescription>
            Query and filters are URL-linked. Submit when you want to run retrieval.
          </AlertDescription>
        </Alert>
      ) : null}

      {ignoredFilterKeys.length > 0 ? (
        <Alert>
          <AlertCircleIcon />
          <AlertTitle>Ignored filter keys</AlertTitle>
          <AlertDescription>{ignoredFilterKeys.join(", ")}</AlertDescription>
        </Alert>
      ) : null}

      {fallbackNotice ? (
        <Alert>
          <AlertCircleIcon />
          <AlertTitle>Partial fallback detected</AlertTitle>
          <AlertDescription>{fallbackNotice}</AlertDescription>
        </Alert>
      ) : null}

      {query.isPending || (query.isFetching && !query.data) ? <LoadingRows /> : null}

      {query.error ? <ErrorNotice error={query.error} /> : null}

      {query.isSuccess && results.length === 0 ? (
        <Alert>
          <SearchIcon />
          <AlertTitle>No evidence found</AlertTitle>
          <AlertDescription>Try broadening your terms or relaxing one or more filters.</AlertDescription>
        </Alert>
      ) : null}

      {query.isSuccess && results.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[2fr_1fr]">
          <div className="rounded-lg border border-border">
            <SearchRows
              results={results}
              evidenceMap={evidenceMap}
              selectedChunkId={selectedChunkId}
              onSelect={setSelectedChunkId}
            />
          </div>
          <div className="space-y-2">
            {selectedEvidence ? (
              <EvidenceCard evidence={selectedEvidence} />
            ) : (
              <Alert>
                <AlertCircleIcon />
                <AlertTitle>No evidence selected</AlertTitle>
                <AlertDescription>Select a result row to inspect full citation provenance.</AlertDescription>
              </Alert>
            )}
          </div>
        </div>
      ) : null}

      {query.isSuccess ? (
        <details className="rounded-lg border border-border p-2 text-xs text-muted-foreground">
          <summary className="cursor-pointer font-medium text-foreground">Retrieval diagnostics</summary>
          <pre className="mt-2 overflow-auto whitespace-pre-wrap">{JSON.stringify(diagnostics ?? {}, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}
