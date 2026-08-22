"use client";

// 본실험 과제 선택 화면 (2026-08-23 T과제 개편) — 친숙/비친숙 2단계 선택을 대체.
//
// 참가자는 상황 기반 과제 4종(T1~T4, lib/studyTasks.ts) 중 **자신의 실제 상황에 맞는
// 2개**를 고른다. 자기선택을 남기는 이유: 과제가 "실제 통근 경로", "실제로 가진 옷"처럼
// 개인 맥락을 요구하므로, 무작위 배정은 맥락이 없는 참가자(통근 안 함 등)에게 허구
// 응답을 강요한다. 진행 순서는 설계가 정한다(선택 2개를 무작위 셔플 — 순서 자기선택
// 편향 차단). 친숙도는 이제 배정 축이 아니라 측정 변수다(지식 행렬 + SPK).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { saveQueue, type PlannedTask } from "@/lib/taskQueue";
import { STUDY_UI } from "@/lib/studyI18n";
import { STUDY_TASKS } from "@/lib/studyTasks";

const NEED = 2; // 과제 2개

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
  const [picked, setPicked] = useState<string[]>([]); // task id 순서 무관 — 시작 시 셔플
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    setParticipantId(new URLSearchParams(window.location.search).get("pid") ?? "");
  }, []);

  const full = picked.length >= NEED;

  const toggle = (id: string) => {
    setPicked((prev) =>
      prev.includes(id)
        ? prev.filter((t) => t !== id)
        : prev.length >= NEED ? prev : [...prev, id],
    );
  };

  const start = () => {
    if (picked.length !== NEED || starting) return;
    setStarting(true);
    // 순서는 설계가 정한다 — 고른 2개를 무작위 셔플 (순서 자기선택 편향 차단).
    const tasks: PlannedTask[] = shuffled(
      STUDY_TASKS.filter((t) => picked.includes(t.id)),
    ).map((t) => ({ category: t.category, familiarity: "none" }));
    saveQueue(participantId || "anon", tasks);
    // 서버에도 계획을 저장 — 진행(남은 과제/다음 과제)의 진실은 서버가 갖는다.
    if (participantId) void api.saveTaskPlan(participantId, tasks).catch(() => {});
    // 첫 세션은 지식 행렬(측정 계획 §4)을 마친 뒤에 연다.
    router.push(participantId ? `/study/knowledge?pid=${participantId}` : "/study/knowledge");
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="msg-in text-xl font-bold text-[#191919]">
        {STUDY_UI.tasks.title}
      </h1>
      <p className="msg-in mt-2 text-sm leading-relaxed text-[#5f6368]" style={{ animationDelay: "60ms" }}>
        {STUDY_UI.tasks.description}
      </p>

      <div className="mt-6 space-y-2">
        {STUDY_TASKS.map((t, i) => {
          const on = picked.includes(t.id);
          const dim = !on && full;
          return (
            <button
              key={t.id}
              onClick={() => toggle(t.id)}
              disabled={dim}
              aria-pressed={on}
              style={{ animationDelay: `${120 + i * 50}ms` }}
              className={`msg-in flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-[border-color,background-color,opacity] duration-150 ${
                on
                  ? "border-[#4f46e5] bg-[#f5f5ff]"
                  : dim
                    ? "cursor-not-allowed border-[#eceff1] bg-[#fafbfc] opacity-60"
                    : "border-[#e4e8eb] bg-white hover:border-[#4f46e5]"
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

      <div className="msg-in mt-6 flex items-center justify-between gap-4" style={{ animationDelay: "340ms" }}>
        <span className="text-xs tabular-nums text-[#9aa0a6]">
          {STUDY_UI.categories.selected(picked.length, NEED)}
        </span>
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
      </div>

    </div>
  );
}
