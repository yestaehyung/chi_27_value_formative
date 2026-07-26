import { PreferenceChip } from "@/lib/types";

// ── 핵심 기준 2~3개 선별 규칙 (UI 수정안 공용) ────────────────────────────
// ⚠ 열린 질문 ③ "무슨 규칙으로 고를지" — 아래는 기본안일 뿐, 이 함수 하나만 바꾸면 됨.
// 기본안: 강한 신호(필수/피하기) > 중요 > 나머지, 같은 급에서는 confidence 높은 순.
// 대안 후보: 작동 빈도(evidenceCount) 순, 최근 등장 순, 사용자 확인(confirmed) 우선 등.
// 이해 확인 문장 — 에이전트 발화 톤(§36 hedged). VariantSession(안 A·B·D·E)과 데모가 공용.
export function understandingSentence(core: PreferenceChip[]): string {
  const labels = core.map((c) => `‘${c.label}’`).join(", ");
  return `지금까지 대화를 보면 ${labels}을(를) 중요하게 보고 계신 것 같아요. 제가 맞게 이해했을까요?`;
}

export function selectCoreCriteria(chips: PreferenceChip[], max = 3): PreferenceChip[] {
  const typeWeight: Record<string, number> = { must_have: 3, avoid: 3, important: 2 };
  return [...chips]
    .sort((x, y) => {
      const tw = (typeWeight[y.type] ?? 1) - (typeWeight[x.type] ?? 1);
      if (tw !== 0) return tw;
      const cf = (y.status === "confirmed" ? 1 : 0) - (x.status === "confirmed" ? 1 : 0);
      if (cf !== 0) return cf;
      return (y.confidence ?? 0) - (x.confidence ?? 0);
    })
    .slice(0, max);
}
