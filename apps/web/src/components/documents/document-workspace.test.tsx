import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  DocumentWorkspaceView,
  selectPreferredArtifact,
  verifyPassageTarget,
} from "@/components/documents/document-workspace";

vi.mock("@/lib/api/client", () => ({
  createApiClient: () => ({
    createSummary: vi.fn(),
    getSummary: vi.fn(),
    createExport: vi.fn(),
    getExport: vi.fn(),
    downloadExport: vi.fn(),
  }),
}));

vi.mock("@/components/summaries/summary-actions", () => ({
  SummaryGenerationPanel: () => <div data-testid="summary-generation-panel" />,
}));

vi.mock("@/components/ui/resizable", () => ({
  ResizableHandle: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ResizablePanelGroup: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/sheet", () => ({
  Sheet: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SheetContent: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  SheetTrigger: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));

describe("selectPreferredArtifact", () => {
  it("prefers a PDF artifact over HTML", () => {
    const artifact = selectPreferredArtifact([
      {
        artifact_id: "html-1",
        content_type: "text/html",
        artifact_kind: "html",
        version_hash: "v1",
        size_bytes: 12,
        created_at: "2026-08-10T00:00:00Z",
      },
      {
        artifact_id: "pdf-1",
        content_type: "application/pdf",
        artifact_kind: "pdf",
        version_hash: "v1",
        size_bytes: 24,
        created_at: "2026-08-10T00:00:00Z",
      },
    ]);

    expect(artifact?.artifact_id).toBe("pdf-1");
  });
});

describe("verifyPassageTarget", () => {
  it("marks route identity as verified and reports mismatches", () => {
    const result = verifyPassageTarget({
      documentId: "doc-1",
      routeVersion: "hash-1",
      routePage: 4,
      routeSection: "section-a",
      passage: {
        document_id: "doc-1",
        chunk_id: "chunk-1",
        section_id: "section-b",
        section_title: "Section B",
        page_number: 5,
        text: "Exact source passage",
        source_url: "https://example.com",
        version_hash: "hash-2",
      },
    });

    expect(result.routeVerified).toBe(true);
    expect(result.versionMatched).toBe(false);
    expect(result.pageMatched).toBe(false);
    expect(result.sectionMatched).toBe(false);
    expect(result.label).toContain("mismatches");
  });
});

describe("DocumentWorkspaceView", () => {
  it("renders header actions and section navigation without a PDF canvas", () => {
    render(
      <DocumentWorkspaceView
        documentId="doc-1"
        metadata={{
          document_id: "doc-1",
          title: "FDA Guidance Example",
          source_url: "https://www.fda.gov/example",
          status: "Final",
          version_hash: "hash-1",
          lifecycle_state: "active",
          center: "CDER",
          issue_date: "2026-08-01",
        }}
        sections={[
          {
            section_id: "section-a",
            section_title: "Section A",
            page_number: 4,
          },
        ]}
        versions={[
          {
            document_id: "doc-1",
            version_hash: "hash-1",
            source_url: "https://www.fda.gov/example",
            status: "Final",
            lifecycle_state: "active",
            created_at: "2026-08-10T00:00:00Z",
          },
        ]}
        artifacts={[]}
        routeState={{ page: 4, version: "hash-1", section: "section-a" }}
        passage={{
          document_id: "doc-1",
          chunk_id: "chunk-1",
          section_id: "section-a",
          section_title: "Section A",
          page_number: 4,
          text: "Exact source passage",
          source_url: "https://www.fda.gov/example",
          version_hash: "hash-1",
        }}
        passageVerification={{
          routeVerified: true,
          versionMatched: true,
          pageMatched: true,
          sectionMatched: true,
          textMatched: null,
          mismatchReasons: [],
          label: "Route and version verified",
        }}
        artifactResource={null}
        artifactError={null}
        selectedArtifactId={null}
        selectedSectionId="section-a"
        onSelectArtifact={vi.fn()}
        onNavigatePage={vi.fn()}
        onNavigateSection={vi.fn()}
        onNavigateVersion={vi.fn()}
        onDownloadArtifact={vi.fn()}
        onOpenArtifact={vi.fn()}
        summaryType="summary"
        onSummaryTypeChange={vi.fn()}
        summarySectionRef={{ current: null }}
        onSummaryCreated={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "FDA Guidance Example" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /summary/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /key changes/i })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /section a/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Exact source passage").length).toBeGreaterThan(0);
  });
});