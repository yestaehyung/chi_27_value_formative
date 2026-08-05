"use client";

// 튜토리얼 본문 — 화면 전환형 코치마크 (재사용 컴포넌트).
//
// 2026-07-27: 사이드 패널이 사라진 E UI에 맞춰 2부를 다시 짰다. 이전 버전은 오른쪽 440px
// 패널(CurrentUnderstandingPanel + ConflictCard + 레이더 그래프)을 설명했는데, 그 화면은
// 더 이상 존재하지 않는다 — 참가자가 없는 UI를 찾게 되므로 반드시 실제 화면과 같아야 한다.
//
// 조건(between-subjects)별로 보여줄 단계가 다르다. 기준을 안 보여주는 baseline 참가자에게
// '기준 확인' 단계를 설명하면 조작(manipulation) 자체가 깨진다 — STEPS의 `conditions`로 거른다.
import { useState } from "react";

import ChatComposer from "@/components/chat/ChatComposer";
import MessageBubble from "@/components/chat/MessageBubble";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ConflictUtterance from "@/components/study/ConflictUtterance";
import SequentialCriteriaConfirm from "@/components/study/SequentialCriteriaConfirm";
import Spotlight, { SpotStep } from "@/components/tutorial/Spotlight";
import { ALLOWS_CORRECTION, SHOWS_CRITERIA, type StudyCondition } from "@/lib/mainSurvey";
import {
  tutorialConflict,
  tutorialImpressions,
  tutorialPreferenceState,
  tutorialTurns,
} from "@/lib/tutorialFixtures";

const DEMO_SCENARIOS = ["운동용 이어폰", "가성비 이어폰", "선물용 이어폰", "겨울 코트", "생일 선물"];

/** 이 단계를 보여줄 조건. 생략하면 전 조건 공통. */
type Step = SpotStep & { conditions?: StudyCondition[] };

// 조건 맵에서 파생한다 — 여기에 슬러그를 다시 적으면 conditions.py와 어긋날 여지가 생긴다.
// 2026-08-06 설계에서는 둘 다 ours 하나뿐이다(baseline1·baseline2 모두 기준을 보여주지 않음).
const SHOWS = (Object.keys(SHOWS_CRITERIA) as StudyCondition[]).filter((c) => SHOWS_CRITERIA[c]);
const EDITS = (Object.keys(ALLOWS_CORRECTION) as StudyCondition[]).filter((c) => ALLOWS_CORRECTION[c]);

const ALL_STEPS: Step[] = [
  // ── 1부: 시나리오 선택 화면 ──
  { selector: '[data-tutorial="compose"]', title: "직접 입력해서 시작해요",
    body: "찾으시는 걸 여기에 적어 바로 시작할 수 있어요.\n예: \"운동할 때 쓸 무선 이어폰 추천해줘\"" },
  { selector: '[data-tutorial="scenarios"]', title: "또는 골라서 시작해요",
    body: "딱히 떠오르지 않으면, 아래 추천 중 하나를 눌러 시작해도 돼요." },

  // ── 2부: 대화 화면 (E UI — 한 컬럼, 사이드 패널 없음) ──
  { selector: '[data-tutorial="chat"]', title: "에이전트와 대화해요",
    body: "원하는 걸 대화로 좁혀가요.\n에이전트가 더 묻거나 후보를 추천해줘요. (위는 예시 대화예요)" },
  { selector: '[data-tutorial="products"]', title: "추천 상품",
    body: "기준에 맞춰 서로 다른 방향의 후보를 보여줘요.\n좌우로 넘기면서 비교할 수 있어요." },
  { selector: '[data-tutorial="card-info"]', title: "카드에서 무엇을 보나요",
    body: "가격·평점·리뷰와 함께, 왜 이 상품을 골랐는지 이유가 적혀 있어요." },
  { selector: '[data-tutorial="card-feedback"]', title: "카드에 반응해요",
    body: "카드 옆 좋아요·싫어요로 취향을 알려주세요.\n반응할수록 추천이 정확해져요." },

  // 조건 의존 — baseline은 기준을 화면에서 보지 않는다
  { selector: '[data-tutorial="criteria-confirm"]', title: "이해가 맞는지 물어봐요",
    body: "대화에서 파악한 기준을 하나씩 확인해요.\n맞으면 '맞아요', 아니면 '아니에요'로 알려주세요 — 틀리게 이해했으면 꼭 바로잡아 주세요.",
    conditions: EDITS },
  { selector: '[data-tutorial="conflict"]', title: "기준이 부딪힐 때",
    body: "앞에서 말씀하신 기준과 다르게 고르신 것 같을 때, 한 번 더 확인해요.\n어느 쪽을 우선할지 골라주시면 바로 반영할게요.",
    conditions: EDITS },
  { selector: '[data-tutorial="anchor"]', title: "지금까지 이해한 기준",
    body: "입력창 위 한 줄에 현재 기준이 모여 있어요.\n펼치면 전체 목록과 '근거'를 볼 수 있어요.",
    conditions: SHOWS },
  { selector: '[data-tutorial="anchor"]', title: "왜 그렇게 이해했는지",
    body: "'근거'를 누르면, 제가 어떤 말·선택을 보고 그렇게 판단했는지 확인할 수 있어요.",
    conditions: SHOWS },

  // 전 조건 공통 — 설문 흐름 예고 (모르고 있다가 만나면 이탈 지점이 된다)
  { selector: '[data-tutorial="composer"]', title: "쇼핑을 마치면",
    body: "충분히 살펴보셨으면 위쪽 '이 쇼핑 마치기'를 눌러주세요.\n마친 뒤 이번 쇼핑에 대한 짧은 질문을 드려요." },
];

export function stepsFor(condition: StudyCondition): Step[] {
  return ALL_STEPS.filter((s) => !s.conditions || s.conditions.includes(condition));
}

export default function TutorialDemo({
  onDone,
  onSkip,
  condition = "ours",
}: {
  onDone: () => void;
  onSkip?: () => void;
  condition?: StudyCondition;
}) {
  const [step, setStep] = useState(0);
  const steps = stepsFor(condition);
  const inSelect = step <= 1; // 0~1 = 시나리오 선택 화면, 2~ = 대화 화면
  const showsCriteria = SHOWS_CRITERIA[condition] ?? true;
  const allowsCorrection = ALLOWS_CORRECTION[condition] ?? true;

  const chips = tutorialPreferenceState.userVisibleSummary.chips;
  const noop = async () => true;

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
        <div className="flex min-h-[calc(100dvh-12rem)] flex-col items-center justify-center">
          <div className="w-full max-w-2xl px-4">
            <h2 className="text-center text-2xl font-bold tracking-tight text-[#191919]">
              <span className="text-[#4f46e5]">에이전트와 쇼핑</span>을 시작해 볼까요?
            </h2>
            <p className="mt-2 text-center text-sm text-[#9aa0a6]">
              찾으시는 걸 입력하거나, 아래 추천에서 골라 시작해 보세요.
            </p>
            <div className="mt-7" data-tutorial="compose">
              <ChatComposer onSend={() => {}} disabled placeholder="무엇을 찾고 계세요?" disclaimer={false} />
            </div>
            <div className="mt-5 flex flex-wrap justify-center gap-2" data-tutorial="scenarios">
              {DEMO_SCENARIOS.map((s) => (
                <span key={s} className="rounded-full border border-[#e4e8eb] bg-white px-4 py-2 text-sm text-[#404040]">
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* ── 2부: 대화 화면 (더미) — 실제 E UI와 같은 한 컬럼 구조.
              no-enter-anim: 한 번에 보여주므로 등장 애니 끔 ── */
        <div className="no-enter-anim mx-auto flex h-[calc(100dvh-12rem)] max-w-3xl flex-col overflow-hidden rounded-2xl border border-[#eef0f2] bg-white">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            <div data-tutorial="chat" className="space-y-3">
              {tutorialTurns.map((t) => (
                <MessageBubble key={t.id} turn={t} />
              ))}
            </div>

            <div data-tutorial="products" className="pl-9">
              <ProductCarousel>
                {tutorialImpressions.map((imp, i) => (
                  <ProductCard
                    key={imp.id}
                    impression={imp}
                    index={i}
                    givenFeedback={[]}
                    onFeedback={() => {}}
                    disabled
                  />
                ))}
              </ProductCarousel>
            </div>

            {/* 기준 확인 — 채팅 안 인라인 (조건에 따라 노출) */}
            {showsCriteria && (
              <div data-tutorial="criteria-confirm" className="pl-9">
                <SequentialCriteriaConfirm
                  askable={chips.slice(0, 2)}
                  alreadyKnown={chips.slice(2, 4)}
                  onConfirm={noop}
                  onReject={noop}
                  onSaveEdit={noop}
                  disabled
                />
              </div>
            )}

            {/* 충돌 — 에이전트 말풍선 (수정 가능 조건만) */}
            {allowsCorrection && (
              <div data-tutorial="conflict">
                <ConflictUtterance conflict={tutorialConflict} onResolve={() => {}} disabled />
              </div>
            )}
          </div>

          {/* 입력창 위 한 줄 앵커 — 실제 화면과 동일 위치 */}
          {showsCriteria && (
            <div data-tutorial="anchor" className="border-t border-[#f0f2f4] bg-[#fafbfc] px-5 py-2">
              <div className="flex w-full items-center gap-1.5 text-left text-xs text-[#5f6368]">
                <span className="font-semibold text-[#9aa0a6]">이해한 기준:</span>
                <span className="min-w-0 flex-1 truncate font-medium text-[#191919]">
                  {chips.slice(0, 3).map((c) => (c.status === "confirmed" ? "✓ " : "") + c.label).join(" · ")}
                </span>
                <span className="shrink-0 text-[#9aa0a6]">▾</span>
              </div>
            </div>
          )}

          <div data-tutorial="composer" className="border-t border-[#f0f2f4] p-3">
            <ChatComposer onSend={() => {}} disabled placeholder="무엇을 찾고 계세요?" />
          </div>
        </div>
      )}

      <Spotlight steps={steps} onDone={onDone} onSkip={onSkip ?? onDone} onStepChange={setStep} />
    </div>
  );
}
