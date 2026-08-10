import DocumentWorkspace from "@/components/documents/document-workspace";

type DocumentPageProps = {
  params: Promise<{ documentId: string }>;
};

export default async function DocumentPage({ params }: DocumentPageProps) {
  const route = await params;

  return <DocumentWorkspace documentId={route.documentId} />;
}
