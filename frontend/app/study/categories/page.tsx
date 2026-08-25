"use client";

// 본실험 과제 선정 화면 (2026-08-24 동결 문서 P0-3) — H/L 2단계 선정.
//
//   1단계  네 과제 후보 중 **가장 잘 안다고 느끼는 제품군** 1개 (H)
//   2단계  나머지 세 후보 중 **가장 잘 모른다고 느끼는 제품군** 1개 (L)
//
// - 후보 카드의 나열 순서는 참가자마다 무작위 (표시 순서를 로그로 남긴다)
// - 두 과제의 진행 순서는 HL/LH 무작위 (sequence로 저장 — 자기선택 편향 차단)
// - H/L은 배정이 아니라 참가자의 상대적 자기선택이다: 시스템 조건만 무작위 조작이며,
//   실제 지식은 지식 행렬(SPK)로 측정해 선정 확인(selection check)으로 보고한다.
// - 제품 지식을 높이거나 낮추는 개입이 없으므로 H/L 차이는 인과효과로 해석하지 않는다.
import { useMemo, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { saveQueue, type PlannedTask } from "@/lib/taskQueue";
import { STUDY_UI } from "@/lib/studyI18n";
import { STUDY_TASKS, type StudyTask } from "@/lib/studyTasks";

function shuffled<T>(items: T[]): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export default function TaskSelectPage() {
  const router = useRouter();
  const [participantId, setParticipantId] = useState("");
  const [step, setStep] = useState<1 | 2>(1);
  const [hTask, setHTask] = useState<string | null>(null); // task id — 가장 잘 아는 것
  const [lTask, setLTask] = useState<string | null>(null); // task id — 가장 잘 모르는 것
  const [starting, setStarting] = useState(false);
  // 후보 나열 순서 — 참가자마다 무작위, 화면 생애 동안 고정 (로그로 저장)
  const displayOrder = useMemo(() => shuffled(STUDY_TASKS), []);

  // 선택 드래프트 (2026-08-25 QA: 새로고침 시 H/L 선택 소실) — 시작 성공 시 삭제
  const DRAFT_KEY = "vc:draft:tasksel";
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      if (raw) {
        const d = JSON.parse(raw);
        if (d?.hTask) setHTask(d.hTask);
        if (d?.lTask) setLTask(d.lTask);
        if (d?.step === 2 && d?.hTask) setStep(2);
      }
    } catch { /* 드래프트 없음/파손 */ }
  }, []);
  useEffect(() => {
    try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ step, hTask, lTask })); } catch { /* quota */ }
  }, [step, hTask, lTask]);

  useEffect(() => {
    setParticipantId(new URLSearchParams(window.location.search).get("pid") ?? "");
  }, []);

  // 2단계 선택지 = 1단계에서 고른 것 제외 (중복 선택 차단)
  const stepOptions = step === 1 ? displayOrder : displayOrder.filter((t) => t.id !== hTask);
  const picked = step === 1 ? hTask : lTask;
  const setPicked = step === 1 ? setHTask : setLTask;

  const goStep2 = () => {
    if (!hTask) return;
    if (lTask === hTask) setLTask(null);
    setStep(2);
  };

  const start = () => {
    if (!hTask || !lTask || hTask === lTask || starting) return;
    setStarting(true);
    const h = STUDY_TASKS.find((t) => t.id === hTask) as StudyTask;
    const l = STUDY_TASKS.find((t) => t.id === lTask) as StudyTask;
    // 진행 순서 HL/LH 무작위 (동결 문서: 조건 내 균형은 배치 규모에서 자연 근사)
    const sequence = Math.random() < 0.5 ? "HL" : "LH";
    const ordered: PlannedTask[] = (sequence === "HL" ? [h, l] : [l, h]).map((t) => ({
      category: t.category,
      familiarity: t.id === hTask ? "familiar" : "unfamiliar", // H=familiar, L=unfamiliar 역할 저장
    }));
    try { sessionStorage.removeItem(DRAFT_KEY); } catch { /* noop */ }
    saveQueue(participantId || "anon", ordered);
    if (participantId) {
      void api.saveTaskPlan(participantId, ordered, {
        candidateDisplayOrder: displayOrder.map((t) => t.id),
        sequence,
        hTaskId: hTask,
        lTaskId: lTask,
      }).catch(() => {});
    }
    router.push(participantId ? `/study/knowledge?pid=${participantId}` : "/study/knowledge");
  };

  return (
    <div key={step} className="mx-auto max-w-3xl px-4 py-8">
      <div className="msg-in text-[11px] font-semibold tabular-nums text-[#9aa0a6]">
        {STUDY_UI.categories.step(step)}
      </div>
      <h1 className="msg-in mt-1 text-xl font-bold text-[#191919]" style={{ animationDelay: "40ms" }}>
        {step === 1 ? STUDY_UI.tasks.hTitle : STUDY_UI.tasks.lTitle}
      </h1>
      <p className="msg-in mt-2 text-sm leading-relaxed text-[#5f6368]" style={{ animationDelay: "80ms" }}>
        {step === 1 ? STUDY_UI.tasks.hDescription : STUDY_UI.tasks.lDescription}
      </p>

      <div className="mt-6 space-y-2">
        {stepOptions.map((t, i) => {
          const on = picked === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setPicked(on ? null : t.id)}
              aria-pressed={on}
              style={{ animationDelay: `${140 + i * 50}ms` }}
              className={`msg-in flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-[border-color,background-color] duration-150 ${
                on ? "border-[#4f46e5] bg-[#f5f5ff]" : "border-[#e4e8eb] bg-white hover:border-[#4f46e5]"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#191919]">{t.title}</div>
                <div className="mt-1 text-xs leading-relaxed text-[#6b7280]">{t.description}</div>
              </div>
              <span
                className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold transition-[background-color,border-color,color] duration-150 ${
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

      <div className="msg-in mt-6 flex items-center justify-end gap-2" style={{ animationDelay: "340ms" }}>
        {step === 2 && (
          <button onClick={() => setStep(1)} className="btn px-4 py-2.5 text-sm">
            {STUDY_UI.categories.back}
          </button>
        )}
        {step === 1 ? (
          <button
            onClick={goStep2}
            disabled={!hTask}
            className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-[background-color,color,scale] duration-150 active:scale-[0.96] ${
              hTask ? "bg-[#4f46e5] text-white hover:bg-[#4338ca]" : "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
            }`}
          >
            {STUDY_UI.categories.next}
          </button>
        ) : (
          <button
            onClick={start}
            disabled={!lTask || starting}
            className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-[background-color,color,scale] duration-150 active:scale-[0.96] ${
              lTask && !starting ? "bg-[#4f46e5] text-white hover:bg-[#4338ca]" : "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
            }`}
          >
            {starting ? STUDY_UI.categories.starting : STUDY_UI.categories.start}
          </button>
        )}
      </div>
    </div>
  );
}
