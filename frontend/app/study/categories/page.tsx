"use client";

// 본실험 카테고리 선택 화면 (2026-08-06, 2026-08-08 개편) — 시나리오 선택을 대체한다.
//
// 참가자는 쇼핑해 볼 상품군 4개를 고르고, 순서는 무작위로 정해진다. 예전의
// "잘 알아요/잘 몰라요" 이분법 분류는 폐기 — 친숙도는 각 과제 직전 설문
// (TPRE_K1/K2 "나는 {카테고리}에 대해 잘 알고 있다")으로 측정한다. 선택 시점
// 이분법은 측정으로서 조악하고(경계 카테고리를 강제로 한쪽에 배정), 설문 문항과
// 이중 측정이 됐다.
//
// 선택지 개수는 N개 일반형으로 짰다 — 지금은 상품 풀이 4개라 사실상 전부 고르게 되지만,
// 카테고리를 늘리면 이 화면은 그대로 두고도 진짜 '선택'이 된다.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { randomOrder, saveQueue } from "@/lib/taskQueue";
import type { CategoryOption } from "@/lib/types";

const NEED_TOTAL = 4; // 쇼핑 과제 수

export default function CategorySelectPage() {
  const router = useRouter();
  const [options, setOptions] = useState<CategoryOption[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(new URLSearchParams(window.location.search).get("pid") ?? "");
    api.categories()
      .then((d) => setOptions(d.categories))
      .catch(() => setError("카테고리를 불러오지 못했어요. 새로고침해 주세요."));
  }, []);

  const ready = picked.length === NEED_TOTAL;
  // 4개가 차면 나머지 카드를 잠근다 — 5개째를 누른 뒤 "왜 안 되지"를 겪지 않도록.
  const locked = (category: string) => ready && !picked.includes(category);

  const toggle = (category: string) => {
    setPicked((prev) =>
      prev.includes(category)
        ? prev.filter((c) => c !== category) // 다시 누르면 해제
        : locked(category) ? prev : [...prev, category],
    );
  };

  const start = async () => {
    if (!ready || starting) return;
    setStarting(true);
    setError(null);
    try {
      // 순서는 여기서 무작위로 확정된다 — 고른 순서가 아니다.
      const tasks = randomOrder(picked);
      saveQueue(participantId || "anon", tasks);
      const res = await api.createCategorySession(tasks[0].category, participantId || undefined);
      router.push(`/study/session/${res.sessionId}`);
    } catch (e) {
      console.error(e);
      setError("쇼핑을 시작하지 못했어요. 다시 눌러 주세요.");
      setStarting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-xl font-bold text-[#191919]">어떤 쇼핑을 해볼까요?</h1>
      <p className="mt-2 text-sm leading-relaxed text-[#5f6368]">
        아래에서 쇼핑해 볼 상품군 <b>{NEED_TOTAL}개</b>를 골라 주세요.
        진행 순서는 무작위로 정해져요.
      </p>

      <div className="mt-6 space-y-2">
        {options.map((o) => {
          const on = picked.includes(o.category);
          const dim = !on && locked(o.category);
          return (
            <button
              key={o.category}
              onClick={() => toggle(o.category)}
              disabled={dim}
              aria-pressed={on}
              className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors ${
                on
                  ? "border-[#4f46e5] bg-[#f5f5ff]"
                  : dim
                    ? "cursor-not-allowed border-[#eceff1] bg-[#fafbfc] opacity-60"
                    : "border-[#e4e8eb] bg-white hover:border-[#4f46e5]"
              }`}
            >
              <span className="text-2xl" aria-hidden>{o.emoji}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#191919]">{o.category}</div>
                {o.blurb && <div className="text-xs text-[#9aa0a6]">{o.blurb}</div>}
              </div>
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
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

      <div className="mt-6 flex items-center justify-between gap-4">
        <span className="text-xs text-[#9aa0a6]">
          선택 {picked.length}/{NEED_TOTAL}
        </span>
        <button
          onClick={start}
          disabled={!ready || starting}
          className={`rounded-xl px-5 py-2.5 text-sm font-semibold transition-colors ${
            ready && !starting
              ? "bg-[#4f46e5] text-white hover:bg-[#4338ca]"
              : "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
          }`}
        >
          {starting ? "시작하는 중…" : "첫 번째 쇼핑 시작"}
        </button>
      </div>

      {error && <p className="mt-3 text-xs text-rose-600">{error}</p>}
    </div>
  );
}
