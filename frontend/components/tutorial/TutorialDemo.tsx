"use client";

// 튜토리얼 본문 — 화면 전환형 코치마크 (재사용 컴포넌트).
// 1부(시나리오 선택 화면): 입력창·시나리오 칩 안내
// 2부(대화 화면): 대화·추천·충돌·기준·근거·그래프 안내
// onDone/onSkip만 받음. 실제 튜토리얼 페이지와 preview 전체플로우가 같이 쓴다.
import { useState } from "react";
import MessageBubble from "@/components/chat/MessageBubble";
import ChatComposer from "@/components/chat/ChatComposer";
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

const DEMO_SCENARIOS = ["운동용 이어폰", "가성비 이어폰", "선물용 이어폰", "겨울 코트", "생일 선물"];

const STEPS: SpotStep[] = [
  // ── 1부: 시나리오 선택 화면 (step 0~1) ──
  { selector: '[data-tutorial="compose"]', title: "직접 입력해서 시작해요",
    body: "찾으시는 걸 여기에 적어 바로 시작할 수 있어요.\n예: \"운동할 때 쓸 무선 이어폰 추천해줘\"" },
  { selector: '[data-tutorial="scenarios"]', title: "또는 골라서 시작해요",
    body: "딱히 떠오르지 않으면, 아래 추천 중 하나를 눌러 시작해도 돼요." },
  // ── 2부: 대화 화면 (step 2~9) ──
  { selector: '[data-tutorial="chat"]', title: "에이전트와 대화해요",
    body: "원하는 걸 대화로 좁혀가요.\n에이전트가 더 묻거나 후보를 추천해줘요. (위는 예시 대화예요)" },
  { selector: '[data-tutorial="products"]', title: "추천 상품 카드",
    body: "기준에 맞춰 서로 다른 방향의 후보 3개를 보여줘요.\n각자 강조점이 달라서, 비교하며 고를 수 있어요." },
  { selector: '[data-tutorial="card-info"]', title: "카드에서 무엇을 보나요",
    body: "가격·평점·리뷰와 함께, ✓는 기준에 맞는 점 / ~는 애매한 점이에요.\n왜 추천했는지 한눈에 볼 수 있어요." },
  { selector: '[data-tutorial="card-feedback"]', title: "카드에 반응해요",
    body: "좋아요·싫어요로 취향을 알려주고, 자세히로 더 살펴보고, 마음에 들면 구매로 최종 선택해요.\n반응할수록 추천이 정확해져요." },
  { selector: '[data-tutorial="conflict"]', title: "기준이 부딪힐 때",
    body: "앞에서 말씀하신 기준과 다르게 고르신 것 같을 때, 한 번 더 확인해요.\n어느 쪽을 우선할지 고르거나 직접 수정하면 바로 반영할게요." },
  { selector: '[data-tutorial="criteria"]', title: "제가 이해한 기준",
    body: "대화에서 파악한 기준이 칩으로 쌓여요.\n맞아요·아니에요로 바로잡거나 '수정'으로 직접 고칠 수 있어요 — 틀리게 이해하면 꼭 고쳐주세요." },
  { selector: '[data-tutorial="evidence"]', title: "왜 그렇게 이해했는지",
    body: "'근거'를 누르면, 제가 어떤 말·선택을 보고 그렇게 판단했는지 확인할 수 있어요." },
  { selector: '[data-tutorial="radars"]', title: "가치·동기 그래프",
    body: "위 그래프는 무엇을 중요하게 보는지(가치), 아래는 이번 쇼핑의 동기예요.\n대화가 쌓일수록 또렷해져요." },
];

export default function TutorialDemo({ onDone, onSkip }: { onDone: () => void; onSkip?: () => void }) {
  const [step, setStep] = useState(0);
  const inSelect = step <= 1; // 0~1 = 시나리오 선택 화면, 2~ = 대화 화면

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-bold">시작 전에, 잠깐 둘러볼게요</h1>
        <p className="mt-1 text-sm text-slate-500">
          {inSelect ? "쇼핑을 시작하는 방법부터 알려드릴게요." : "대화 화면의 핵심 기능을 짚어드릴게요."}
        </p>
      </div>

      {inSelect ? (
        /* ── 1부: 시나리오 선택 화면 (더미) ── */
        <div className="flex min-h-[calc(100vh-12rem)] flex-col items-center justify-center">
          <div className="w-full max-w-2xl px-4">
            <h2 className="text-center text-2xl font-bold tracking-tight text-[#191919]">
              <span className="text-[#4f46e5]">에이전트와 쇼핑</span>을 시작해 볼까요?
            </h2>
            <p className="mt-2 text-center text-sm text-[#9aa0a6]">찾으시는 걸 입력하거나, 아래 추천에서 골라 시작해 보세요.</p>
            <div className="mt-7" data-tutorial="compose">
              <ChatComposer onSend={() => {}} disabled placeholder="무엇을 찾고 계세요?" disclaimer={false} />
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-2" data-tutorial="scenarios">
              {DEMO_SCENARIOS.map((s) => (
                <span key={s} className="rounded-full border border-[#e4e8eb] bg-white px-4 py-2 text-sm text-[#404040]">{s}</span>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* ── 2부: 대화 화면 (더미) — no-enter-anim: 한 번에 보여주므로 등장 애니 끔 ── */
        <div className="no-enter-anim grid h-[calc(100vh-12rem)] grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
          <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[#eef0f2] bg-white">
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              <div data-tutorial="chat" className="space-y-3">
                {tutorialTurns.map((t) => <MessageBubble key={t.id} turn={t} />)}
              </div>
              <div data-tutorial="products" className="pl-9">
                <div className="flex gap-3 overflow-x-auto pb-2">
                  {tutorialImpressions.map((imp, i) => (
                    <div key={imp.id} className="w-[284px] shrink-0">
                      <ProductCard impression={imp} index={i} givenFeedback={[]} onFeedback={() => {}} disabled />
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="border-t border-[#f0f2f4] p-3">
              <ChatComposer onSend={() => {}} disabled placeholder="무엇을 찾고 계세요?" />
            </div>
          </div>

          <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
            <div data-tutorial="conflict">
              <ConflictCard conflict={tutorialConflict} onResolve={() => {}} />
            </div>
            <CurrentUnderstandingPanel state={tutorialPreferenceState} onChipAction={() => {}} onShowEvidence={() => {}} />
          </div>
        </div>
      )}

      <Spotlight steps={STEPS} onDone={onDone} onSkip={onSkip ?? onDone} onStepChange={setStep} />
    </div>
  );
}
