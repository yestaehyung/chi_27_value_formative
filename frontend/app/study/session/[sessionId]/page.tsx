"use client";

// 참가자 스터디 세션 페이지 (2026-07-21) — 실제 UI를 안 E로 반영.
// 사이드바 없이 채팅 인라인 + 에이전트 순차 확인(SequentialCriteriaConfirm) +
// 입력창 위 앵커 + 충돌 발화. 세션 생명주기(마치기/사후설문/첫 발화 자동전송)는
// study 플래그로 VariantSession이 담당한다. 이전 "지금 버전"(사이드바+칩+레이더)은
// components/study/CurrentStudySession.tsx로 보존 — /study/compare 비교 도구에서 사용.

import { useParams } from "next/navigation";
import VariantSession from "@/components/study/VariantSession";

export default function StudySessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  return <VariantSession sessionId={sessionId} variant="e" study />;
}
