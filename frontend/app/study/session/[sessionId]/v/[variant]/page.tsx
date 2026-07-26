import { notFound } from "next/navigation";
import VariantSession, { UiVariant } from "@/components/study/VariantSession";

// UI 수정안 라우트 — /study/session/{id}/v/a (안 A) · /v/b (안 B) · /v/c (수정안 3, 경량 패널) · /v/d (솔리드 카드) · /v/e (에이전트 능동 질문).
// 기존 /study/session/{id} (지금 버전)는 건드리지 않는다. 토글 비교는 /study/session/{id}/compare.
export default function VariantSessionPage({
  params,
}: {
  params: { sessionId: string; variant: string };
}) {
  if (!["a", "b", "c", "d", "e"].includes(params.variant)) notFound();
  return <VariantSession sessionId={params.sessionId} variant={params.variant as UiVariant} />;
}
