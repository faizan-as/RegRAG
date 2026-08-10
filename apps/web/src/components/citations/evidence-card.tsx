import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";

type EvidenceCardModel = components["schemas"]["EvidenceCard"];

function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "-";
  }
  return value.toFixed(4);
}

export function buildEvidenceDocumentHref(evidence: EvidenceCardModel): string {
  const query = new URLSearchParams();
  query.set("chunk", evidence.chunk_id);
  if (evidence.section_id) {
    query.set("section", evidence.section_id);
  }
  if (evidence.page_number !== null && evidence.page_number !== undefined) {
    query.set("page", String(evidence.page_number));
  }
  if (evidence.version_hash) {
    query.set("version", evidence.version_hash);
  }

  return `/documents/${encodeURIComponent(evidence.document_id)}?${query.toString()}`;
}

export function EvidenceCard({ evidence }: { evidence: EvidenceCardModel }) {
  const passageSection = evidence.section_title || evidence.section_id || "Unlabeled section";

  return (
    <article className="rounded-lg border border-border bg-card p-3 text-sm">
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="h-5">{evidence.citation_id}</Badge>
        <Badge variant="secondary" className="h-5">{evidence.document_status}</Badge>
        <p className="font-medium text-foreground">{evidence.title}</p>
      </header>

      <p className="mb-2 line-clamp-5 whitespace-pre-wrap text-sm text-muted-foreground">{evidence.passage}</p>

      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-muted-foreground sm:grid-cols-2">
        <div>
          <dt className="inline text-foreground">Section: </dt>
          <dd className="inline">{passageSection}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Page: </dt>
          <dd className="inline">{evidence.page_number ?? "-"}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Chunk: </dt>
          <dd className="inline">{evidence.chunk_id}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Version: </dt>
          <dd className="inline">{evidence.version_hash}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Retrieval: </dt>
          <dd className="inline">{formatNumber(evidence.retrieval_score)}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Rerank: </dt>
          <dd className="inline">{formatNumber(evidence.rerank_score)}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Confidence: </dt>
          <dd className="inline">{formatNumber(evidence.confidence)}</dd>
        </div>
        <div>
          <dt className="inline text-foreground">Retrieved: </dt>
          <dd className="inline">{evidence.retrieved_at ?? "-"}</dd>
        </div>
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link
          href={buildEvidenceDocumentHref(evidence)}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Open source passage
        </Link>
        <a
          href={evidence.source_url}
          target="_blank"
          rel="noreferrer"
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          FDA source
        </a>
      </div>
    </article>
  );
}
