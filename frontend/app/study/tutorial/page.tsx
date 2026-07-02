"use client";

// 참가자 튜토리얼 — 리디자인 플로우(시작 화면 → 대화)에 맞춘 화면 전환형 코치마크 (2026-07-02).
// 본문은 TutorialDemo(재사용 컴포넌트, 프리뷰에서 확정 — 1부 시작화면 안내 + 2부 대화화면
// 안내 10단계)가 담당하고, 이 페이지는 설문에서 넘어온 pid를 시작 화면으로 전달만 한다.
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import TutorialDemo from "@/components/tutorial/TutorialDemo";

function TutorialInner() {
  const router = useRouter();
  const pid = useSearchParams().get("pid");
  const done = () => router.push(pid ? `/study/session/new?pid=${pid}` : "/study/session/new");
  return <TutorialDemo onDone={done} onSkip={done} />;
}

export default function TutorialPage() {
  return (
    <Suspense fallback={null}>
      <TutorialInner />
    </Suspense>
  );
}
