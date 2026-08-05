"use client";

// 참가자 튜토리얼 — 리디자인 플로우(시작 화면 → 대화)에 맞춘 화면 전환형 코치마크.
// 본문은 TutorialDemo(재사용 컴포넌트)가 담당하고, 이 페이지는 설문에서 넘어온
// pid·조건을 전달만 한다.
//
// 조건을 URL로 받는 이유: 참가자 조건을 읽는 API는 연구자 키로 잠겨 있고, 사전 설문
// 응답에 이미 배정 결과가 들어 있다. 여기서 새 엔드포인트를 열 이유가 없다.
// (조건이 없으면 correctable로 폴백 — 로컬에서 URL을 직접 열어보는 경우)
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import TutorialDemo from "@/components/tutorial/TutorialDemo";
import { SHOWS_CRITERIA, type StudyCondition } from "@/lib/mainSurvey";

function TutorialInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pid = params.get("pid");
  const raw = params.get("cond");
  const condition: StudyCondition =
    raw && raw in SHOWS_CRITERIA ? (raw as StudyCondition) : "ours";

  // 튜토리얼 다음은 카테고리 선택 — 시나리오 선택(/study/session/new)을 대체했다(2026-08-06).
  const done = () => router.push(pid ? `/study/categories?pid=${pid}` : "/study/categories");
  return <TutorialDemo onDone={done} onSkip={done} condition={condition} />;
}

export default function TutorialPage() {
  return (
    <Suspense fallback={null}>
      <TutorialInner />
    </Suspense>
  );
}
