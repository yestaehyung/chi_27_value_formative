"use client";

// 본실험 카테고리 선택 화면 (2026-08-06 · 2026-08-08 2단계 개편) — 시나리오 선택을 대체.
//
// 2단계 플로우:
//   1단계  평소 잘 아는 상품군 2개 선택
//   2단계  (남은 것 중) 잘 모르는 상품군 2개 선택
//   → (친숙 1 → 비친숙 1) 묶음 × 2 순서로 첫 쇼핑 시작 (측 내부만 무작위)
//
// 왜 두 단계로 나누나: 한 화면에서 카드마다 "잘 알아요/잘 몰라요"를 고르게 하면 두
// 판단이 섞여 기준이 흐려진다. 단계를 나누면 참가자가 한 번에 한 질문("아는 것은?" →
// "모르는 것은?")만 생각한다. 친숙도는 within-subjects 요인으로 세션에 남고, 과제 직전
// 설문(TPRE_K1/K2)이 이 이분법의 조작 점검이 된다.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { pairedOrder, saveQueue } from "@/lib/taskQueue";
import type { CategoryOption } from "@/lib/types";
import { categoryBlurb, categoryLabel, STUDY_UI } from "@/lib/studyI18n";

const NEED_PER_SIDE = 2; // 친숙 2 + 비친숙 2

export default function CategorySelectPage() {
  const router = useRouter();
  const [options, setOptions] = useState<CategoryOption[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [step, setStep] = useState<1 | 2>(1);
  const [familiar, setFamiliar] = useState<string[]>([]);
  const [unfamiliar, setUnfamiliar] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(new URLSearchParams(window.location.search).get("pid") ?? "");
    api.categories()
      .then((d) => setOptions(d.categories))
      .catch(() => setError(STUDY_UI.categories.loadError));
  }, []);

  // 2단계 선택지 = 1단계에서 고르지 않은 것만 — "아는 것"으로 이미 분류한 카테고리를
  // 다시 보여주면 참가자가 같은 판단을 두 번 한다.
  const stepOptions = step === 1 ? options : options.filter((o) => !familiar.includes(o.category));
  const picked = step === 1 ? familiar : unfamiliar;
  const setPicked = step === 1 ? setFamiliar : setUnfamiliar;
  const full = picked.length >= NEED_PER_SIDE;

  const toggle = (category: string) => {
    setPicked((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category) // 다시 누르면 해제
        : prev.length >= NEED_PER_SIDE ? prev : [...prev, category],
    );
  };

  const goStep2 = () => {
    // 1단계 선택을 바꿨을 수 있으니, 이제 친숙으로 분류된 것은 비친숙 선택에서 걷어낸다
    setUnfamiliar((prev) => prev.filter((c) => !familiar.includes(c)));
    setStep(2);
  };

  const start = () => {
    if (familiar.length !== NEED_PER_SIDE || unfamiliar.length !== NEED_PER_SIDE || starting) return;
    setStarting(true);
    // 순서는 여기서 확정된다 — (친숙→비친숙) 묶음 × 2, 측 내부만 무작위.
    const tasks = pairedOrder(familiar, unfamiliar);
    saveQueue(participantId || "anon", tasks);
    // 서버에도 계획을 저장 — 진행(남은 과제/다음 과제)의 진실은 서버가 갖는다.
    // 실패해도 진행은 막지 않는다(로컬 큐 폴백); 서버 저장은 유실 대비 안전망.
    if (participantId) void api.saveTaskPlan(participantId, tasks).catch(() => {});
    // 첫 세션은 지식 행렬(측정 계획 §4)을 마친 뒤에 연다 — "초기" 지식·기준이
    // 대화에 오염되기 전에 잠겨야 한다.
    router.push(participantId ? `/study/knowledge?pid=${participantId}` : "/study/knowledge");
  };

  return (
    // key={step}: 단계가 바뀌면 서브트리를 새로 마운트해 스태거 진입이 다시 재생된다
    <div key={step} className="mx-auto max-w-3xl px-4 py-8">
      {/* 진입: 단계 배지 → 제목 → 카드(순차) → 푸터를 ~60ms 간격으로 스태거 */}
      <div className="msg-in text-[11px] font-semibold tabular-nums text-[#9aa0a6]">
        {STUDY_UI.categories.step(step)}
      </div>
      <h1 className="msg-in mt-1 text-xl font-bold text-[#191919]" style={{ animationDelay: "40ms" }}>
        {step === 1 ? STUDY_UI.categories.familiarTitle : STUDY_UI.categories.unfamiliarTitle}
      </h1>
      <p className="msg-in mt-2 text-sm leading-relaxed text-[#5f6368]" style={{ animationDelay: "80ms" }}>
        {step === 1
          ? STUDY_UI.categories.familiarDescription
          : STUDY_UI.categories.unfamiliarDescription}
      </p>

      <div className="mt-6 space-y-2">
        {stepOptions.map((o, i) => {
          const on = picked.includes(o.category);
          const dim = !on && full;
          return (
            <button
              key={o.category}
              onClick={() => toggle(o.category)}
              disabled={dim}
              aria-pressed={on}
              style={{ animationDelay: `${140 + i * 50}ms` }}
              className={`msg-in flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-[border-color,background-color,opacity] duration-150 ${
                on
                  ? "border-[#4f46e5] bg-[#f5f5ff]"
                  : dim
                    ? "cursor-not-allowed border-[#eceff1] bg-[#fafbfc] opacity-60"
                    : "border-[#e4e8eb] bg-white hover:border-[#4f46e5]"
              }`}
            >
              {/* 이모지 없음 (2026-08-08) — 브랜드 톤(인디고·절제)과 어긋나서 텍스트만 쓴다 */}
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#191919]">{categoryLabel(o.category)}</div>
                {o.blurb && <div className="mt-0.5 text-xs text-[#9aa0a6]">{categoryBlurb(o.blurb)}</div>}
              </div>
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold transition-[background-color,border-color,color] duration-150 ${
                  on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#d5d9dd] text-transparent"
                }`}
                aria-hidden
              >
                ✓
              </span>
            </button>
          );
        })}
      </div>

      <div className="msg-in mt-6 flex items-center justify-between gap-4" style={{ animationDelay: "340ms" }}>
        {/* tabular-nums: 0/2 → 2/2 변해도 폭이 흔들리지 않게 */}
        <span className="text-xs tabular-nums text-[#9aa0a6]">
          {STUDY_UI.categories.selected(picked.length, NEED_PER_SIDE)}
        </span>
        <div className="flex items-center gap-2">
          {step === 2 && (
            <button
              onClick={() => setStep(1)}
              className="btn px-4 py-2.5 text-sm"
            >
              {STUDY_UI.categories.back}
            </button>
          )}
          {step === 1 ? (
            <button
              onClick={goStep2}
              disabled={!full}
              className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-[background-color,color,scale] duration-150 active:scale-[0.96] ${
                full
                  ? "bg-[#4f46e5] text-white hover:bg-[#4338ca]"
                  : "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
              }`}
            >
              {STUDY_UI.categories.next}
            </button>
          ) : (
            <button
              onClick={start}
              disabled={!full || starting}
              className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-[background-color,color,scale] duration-150 active:scale-[0.96] ${
                full && !starting
                  ? "bg-[#4f46e5] text-white hover:bg-[#4338ca]"
                  : "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
              }`}
            >
              {starting ? STUDY_UI.categories.starting : STUDY_UI.categories.start}
            </button>
          )}
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
