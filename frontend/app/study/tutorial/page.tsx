"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import MessageBubble from "@/components/chat/MessageBubble";
import UserInputBox from "@/components/chat/UserInputBox";
import ProductCard from "@/components/products/ProductCard";
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import ConflictCard from "@/components/preference/ConflictCard";
import Spotlight, { SpotStep } from "@/components/tutorial/Spotlight";
import {
  tutorialTurns,
  tutorialImpressions,
  tutorialPreferenceState,
  tutorialConflict,
} from "@/lib/tutorialFixtures";

const STEPS: SpotStep[] = [
  {
    selector: '[data-tutorial="chat"]',
    title: "에이전트와 대화해요",
    body: "원하는 걸 대화로 좁혀가요.\n아래 입력창에 무엇을 찾는지 적으면, 에이전트가 더 묻거나 후보를 추천해줘요. (위는 예시 대화예요)",
  },
  {
    selector: '[data-tutorial="products"]',
    title: "추천 상품 카드",
    body: "기준에 맞춰 서로 다른 방향의 후보 3개를 보여줘요.\n각 카드 아래 좋아요·싫어요로 반응하면 취향을 학습하고, 자세히로 더 살펴보고, 마음에 들면 구매로 최종 선택해요.",
  },
  {
    selector: '[data-tutorial="conflict"]',
    title: "기준이 부딪힐 때",
    body: "앞에서 말씀하신 기준과 다르게 고르신 것 같을 때, 한 번 더 확인해요.\n어느 쪽을 우선할지 고르거나 직접 수정하면 바로 반영할게요.",
  },
  {
    selector: '[data-tutorial="criteria"]',
    title: "제가 이해한 기준",
    body: "대화에서 파악한 기준이 칩으로 쌓여요.\n맞아요·아니에요로 바로잡거나 '수정'으로 직접 고칠 수 있어요 — 제가 틀리게 이해하면 꼭 고쳐주세요.",
  },
  {
    selector: '[data-tutorial="evidence"]',
    title: "왜 그렇게 이해했는지",
    body: "'근거'를 누르면, 제가 어떤 말·선택을 보고 그렇게 판단했는지 확인할 수 있어요.",
  },
  {
    selector: '[data-tutorial="radars"]',
    title: "가치·동기 그래프",
    body: "위 그래프는 무엇을 중요하게 보는지(가치), 아래는 이번 쇼핑의 동기예요.\n대화가 쌓일수록 점점 또렷해져요.",
  },
];

function TutorialInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pid = params.get("pid");

  const start = () => router.push(pid ? `/study/session/new?pid=${pid}` : "/study/session/new");

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-bold">시작 전에, 잠깐 둘러볼게요</h1>
        <p className="mt-1 text-sm text-slate-500">실제 쇼핑 대화 화면이에요. 핵심 기능 6가지만 짚어드릴게요.</p>
      </div>

      {/* 실제 세션과 동일한 2단 레이아웃 (더미 데이터, 클릭은 동작 안 함) */}
      <div className="grid h-[calc(100vh-12rem)] grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
        {/* 좌: 대화 + 추천 + 입력창 */}
        <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[#eef0f2] bg-white">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            <div data-tutorial="chat" className="space-y-3">
              {tutorialTurns.map((t) => (
                <MessageBubble key={t.id} turn={t} />
              ))}
            </div>
            {/* 실제 세션과 동일한 가로 캐러셀 (에이전트 메시지 아래 pl-9 들여쓰기) */}
            <div data-tutorial="products" className="pl-9">
              <div className="flex gap-3 overflow-x-auto pb-2">
                {tutorialImpressions.map((imp, i) => (
                  <div key={imp.id} className="w-[284px] shrink-0">
                    <ProductCard
                      impression={imp}
                      index={i}
                      givenFeedback={[]}
                      onFeedback={() => {}}
                      disabled
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <UserInputBox onSend={() => {}} disabled />
        </div>

        {/* 우: 충돌 카드 + 이해 패널 (실제 세션과 동일 순서) */}
        <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
          <div data-tutorial="conflict">
            <ConflictCard conflict={tutorialConflict} onResolve={() => {}} />
          </div>
          <CurrentUnderstandingPanel
            state={tutorialPreferenceState}
            onChipAction={() => {}}
            onShowEvidence={() => {}}
          />
        </div>
      </div>

      <Spotlight steps={STEPS} onDone={start} onSkip={start} />
    </div>
  );
}

export default function TutorialPage() {
  return (
    <Suspense fallback={null}>
      <TutorialInner />
    </Suspense>
  );
}
