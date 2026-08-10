import { ChatWorkspace } from "@/components/chat/chat-workspace";

type SessionPageProps = {
  params: Promise<{ sessionId: string }>;
};

export default async function SessionPage({ params }: SessionPageProps) {
  const { sessionId } = await params;
  return <ChatWorkspace sessionId={sessionId} />;
}
