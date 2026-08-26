// 종료 절차 상태 판정 — 단일 진실 (D3, 2026-08-26).
//
// 종료 단계의 진실은 세션 meta에 저장된 사실들(finalChoice·postSurvey·criterionAudit)
// 이다. 이전에는 이 사실 조합의 해석이 VariantSession 로드부에 분기 3개로 흩어져
// 사고 때마다 하나씩 늘었다 — 해석을 이 함수 하나로 모은다. 별도 스테이지 필드를
// 저장하지 않는 이유: 이미 수집된 세션(b1 30명)에는 그 필드가 없어 이중 해석
// 경로가 생기고, 진실의 원천이 둘이 되면 어긋날 일만 남는다.
//
// 단계 전이 (순서 고정):
//   shopping → (최종 선택 확정) → cc(final일 때만) → audit → done

export type FinishStage = "shopping" | "cc" | "audit" | "done";

type SessionMeta = {
  finalChoice?: { status?: string } | null;
  postSurvey?: unknown;
  criterionAudit?: unknown;
} | null | undefined;

export function finishStageOf(meta: SessionMeta): FinishStage {
  const fc = meta?.finalChoice;
  if (!fc) return "shopping";
  // CC(선택 확신)는 "하나의 상품을 최종 선택했다"에만 제시 — 그 외 상태는 NA로 건너뜀
  if (fc.status === "final" && !meta?.postSurvey) return "cc";
  if (!meta?.criterionAudit) return "audit";
  return "done";
}
