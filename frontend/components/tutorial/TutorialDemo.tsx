"use client";

// 튜토리얼 본문 — 화면 전환형 코치마크 (재사용 컴포넌트).
//
// 2026-08-11: 본실험 UI 개편에 맞춰 다시 짰다. 참가자가 실제로 만나는 화면과 반드시
// 같아야 한다 — 없는 UI를 가르치면 참가자가 그걸 찾다가 길을 잃는다.
//   1부  카테고리 선택 (2단계: 잘 아는 것 2개 → 잘 모르는 것 2개, 순서는 무작위)
//   2부  대화 화면 — ours는 채팅 + 우측 사이드바(기준 칩·충돌 카드, 레이더 없음),
//        baseline1·2는 사이드바 없는 단일 컬럼
//
// 조건(between-subjects)별로 보여줄 단계가 다르다. 기준을 안 보여주는 baseline 참가자에게
// '기준 확인' 단계를 설명하면 조작(manipulation) 자체가 깨진다 — STEPS의 `conditions`로 거른다.
import { useState } from "react";

import ChatComposer from "@/components/chat/ChatComposer";
import MessageBubble from "@/components/chat/MessageBubble";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ConflictCard from "@/components/preference/ConflictCard";
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import Spotlight, { SpotStep } from "@/components/tutorial/Spotlight";
import { ALLOWS_CORRECTION, SHOWS_CRITERIA, type StudyCondition } from "@/lib/mainSurvey";
import {
  tutorialConflict,
  tutorialImpressions,
  tutorialPreferenceState,
  tutorialTurns,
} from "@/lib/tutorialFixtures";
import { STUDY_UI } from "@/lib/studyI18n";

// 카테고리 선택 미리보기 더미 — 실제 풀과 같은 이름을 쓰되, 여기서는 표시만 한다.
const DEMO_CATEGORIES = STUDY_UI.tutorial.demoCategories;

/** 이 단계를 보여줄 조건. 생략하면 전 조건 공통. */
type Step = SpotStep & { conditions?: StudyCondition[] };

// 조건 맵에서 파생한다 — 여기에 슬러그를 다시 적으면 conditions.py와 어긋날 여지가 생긴다.
// 2026-08-06 설계에서는 둘 다 ours 하나뿐이다(baseline1·baseline2 모두 기준을 보여주지 않음).
const SHOWS = (Object.keys(SHOWS_CRITERIA) as StudyCondition[]).filter((c) => SHOWS_CRITERIA[c]);
const EDITS = (Object.keys(ALLOWS_CORRECTION) as StudyCondition[]).filter((c) => ALLOWS_CORRECTION[c]);

const STEP_CONDITIONS: Partial<Record<string, StudyCondition[]>> = {
  panel: SHOWS, criteria: EDITS, evidence: SHOWS, conflict: EDITS,
};
const ALL_STEPS: Step[] = STUDY_UI.tutorial.steps.map((step) => ({
  selector: `[data-tutorial="${step.key}"]`,
  title: step.title,
  body: step.body,
  conditions: STEP_CONDITIONS[step.key],
}));

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
  const inSelect = step === 0; // 0 = 카테고리 선택 화면, 1~ = 대화 화면
  const showsCriteria = SHOWS_CRITERIA[condition] ?? true;
  const allowsCorrection = ALLOWS_CORRECTION[condition] ?? true;

  const noop = async () => true;

  return (
    <div className="space-y-3">
      <div>
        <h1 className="text-xl font-bold">{STUDY_UI.tutorial.pageTitle}</h1>
        <p className="mt-1 text-sm text-slate-500">
          {inSelect ? STUDY_UI.tutorial.categoryIntro : STUDY_UI.tutorial.chatIntro}
        </p>
      </div>

      {inSelect ? (
        /* ── 1부: 카테고리 선택 화면 (더미) — 실제 /study/categories 1단계와 같은 모양 ── */
        <div className="flex min-h-[calc(100dvh-12rem)] flex-col items-center justify-center">
          <div className="w-full max-w-2xl px-4" data-tutorial="categories">
            <div className="text-[11px] font-semibold tabular-nums text-[#9aa0a6]">{STUDY_UI.categories.step(1)}</div>
            <h2 className="mt-1 text-xl font-bold text-[#191919]">{STUDY_UI.categories.familiarTitle}</h2>
            <p className="mt-2 text-sm leading-relaxed text-[#5f6368]">
              {STUDY_UI.categories.familiarDescription}
            </p>
            <div className="mt-5 space-y-2">
              {DEMO_CATEGORIES.map((c) => (
                <div
                  key={c.name}
                  className={`flex items-center gap-3 rounded-xl border p-3 ${
                    c.on ? "border-[#4f46e5] bg-[#f5f5ff]" : "border-[#e4e8eb] bg-white"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-[#191919]">{c.name}</div>
                    <div className="mt-0.5 text-xs text-[#9aa0a6]">{c.blurb}</div>
                  </div>
                  <span
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
                      c.on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#d5d9dd] text-transparent"
                    }`}
                    aria-hidden
                  >
                    ✓
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        /* ── 2부: 대화 화면 (더미) — 실제 세션 UI와 같은 구조.
              ours: 채팅 + 우측 사이드바 / baseline: 단일 컬럼.
              no-enter-anim: 한 번에 보여주므로 등장 애니 끔 ── */
        <div
          className={`no-enter-anim mx-auto grid h-[calc(100dvh-12rem)] gap-4 ${
            showsCriteria ? "max-w-6xl grid-cols-1 lg:grid-cols-[minmax(0,1fr)_440px]" : "max-w-3xl grid-cols-1"
          }`}
        >
          <div className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-[#eef0f2] bg-white">
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
            </div>

            <div data-tutorial="composer" className="border-t border-[#f0f2f4] p-3">
              <ChatComposer onSend={() => {}} disabled placeholder={STUDY_UI.chat.inputPlaceholder} />
            </div>
          </div>

          {/* 우측 사이드바 — 실제 studyPanel과 동일 구성 (충돌 카드 + 기준 패널, 레이더 없음) */}
          {showsCriteria && (
            <div data-tutorial="panel" className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
              {allowsCorrection && (
                <div data-tutorial="conflict">
                  <ConflictCard conflict={tutorialConflict} onResolve={() => {}} disabled />
                </div>
              )}
              <CurrentUnderstandingPanel
                state={tutorialPreferenceState}
                showRadar={false}
                editable={allowsCorrection}
                onChipAction={noop}
                onShowEvidence={() => {}}
              />
            </div>
          )}
        </div>
      )}

      <Spotlight steps={steps} onDone={onDone} onSkip={onSkip ?? onDone} onStepChange={setStep} />
    </div>
  );
}
