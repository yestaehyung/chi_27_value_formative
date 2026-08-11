"use client";

// 참가자 스터디 세션 페이지 (2026-07-21, 2026-08-08 사이드바 복귀) — 본실험 UI.
// study 플래그 + ours 조건이면 VariantSession이 우측 사이드바(기준 칩 + 충돌 카드,
// 방사형 그래프 2종은 본실험에서 제외)를 켜고 E의 인라인 위젯을 끈다. baseline1·2는
// 사이드바 없는 단일 컬럼. 세션 생명주기(설문·과제 큐·마치기)는 VariantSession 담당.
// 원본 사이드바 UI(레이더 포함)는 components/study/CurrentStudySession.tsx로 보존
// — /study/compare 비교 도구에서 사용.

import { useParams } from "next/navigation";
import VariantSession from "@/components/study/VariantSession";

export default function StudySessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  return <VariantSession sessionId={sessionId} variant="e" study />;
}
