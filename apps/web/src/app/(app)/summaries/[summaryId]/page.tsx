import { SummaryWorkspace } from "@/components/summaries/summary-workspace";

type SummaryPageProps = {
  params: Promise<{ summaryId: string }>;
};

export default async function SummaryPage({ params }: SummaryPageProps) {
  const { summaryId } = await params;

  return <SummaryWorkspace summaryId={summaryId} />;
}