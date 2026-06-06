import { notFound } from "next/navigation";
import { getDecision } from "@/lib/api/decisions";
import { DecisionDetail } from "@/components/decisions/decision-detail";

export const revalidate = 30;

interface Props {
  params: Promise<{ id: string; decisionId: string }>;
}

export default async function DecisionDetailPage({ params }: Props) {
  const { id: repoId, decisionId } = await params;

  let decision;
  try {
    decision = await getDecision(repoId, decisionId);
  } catch {
    notFound();
  }

  return (
    <div className="max-w-3xl p-6">
      <DecisionDetail decision={decision} repoId={repoId} />
    </div>
  );
}
