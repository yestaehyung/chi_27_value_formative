"use client";

// 본실험 카테고리 선택 화면 (2026-08-06) — 시나리오 선택(/study/session/new)을 대체한다.
//
// 참가자는 각 카테고리를 "익숙하다 / 낯설다"로 나누고, 그중 익숙 2개 + 낯선 2개를 골라
// 네 번의 쇼핑을 한다. 친숙도는 시나리오에 고정할 수 없는 값(사람마다 다름)이라
// 참가자가 선택 시점에 직접 매기고, 그 값이 세션에 남아 within-subjects 요인이 된다.
//
// 선택지 개수는 N개 일반형으로 짰다 — 지금은 상품 풀이 4개라 사실상 전부 고르게 되지만,
// 카테고리를 늘리면 이 화면은 그대로 두고도 진짜 '선택'이 된다.
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { interleave, saveQueue } from "@/lib/taskQueue";
import type { CategoryOption, Familiarity } from "@/lib/types";

const NEED_PER_SIDE = 2; // 익숙 2 + 낯선 2

export default function CategorySelectPage() {
  const router = useRouter();
  const [options, setOptions] = useState<CategoryOption[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [picks, setPicks] = useState<Record<string, Familiarity>>({});
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setParticipantId(new URLSearchParams(window.location.search).get("pid") ?? "");
    api.categories()
      .then((d) => setOptions(d.categories))
      .catch(() => setError("카테고리를 불러오지 못했어요. 새로고침해 주세요."));
  }, []);

  const familiar = useMemo(
    () => Object.entries(picks).filter(([, f]) => f === "familiar").map(([c]) => c),
    [picks],
  );
  const unfamiliar = useMemo(
    () => Object.entries(picks).filter(([, f]) => f === "unfamiliar").map(([c]) => c),
    [picks],
  );
  const ready = familiar.length === NEED_PER_SIDE && unfamiliar.length === NEED_PER_SIDE;

  // 한쪽이 이미 2개면 그쪽 버튼을 잠근다 — 3개째를 누른 뒤 "왜 안 되지"를 겪지 않도록,
  // 누를 수 없다는 걸 미리 보여준다.
  const locked = (f: Familiarity) =>
    (f === "familiar" ? familiar.length : unfamiliar.length) >= NEED_PER_SIDE;

  const choose = (category: string, f: Familiarity) => {
    setPicks((prev) => {
      const next = { ...prev };
      if (next[category] === f) delete next[category]; // 다시 누르면 해제
      else if (!locked(f) || prev[category] === f) next[category] = f;
      return next;
    });
  };

  const start = async () => {
    if (!ready || starting) return;
    setStarting(true);
    setError(null);
    try {
      const tasks = interleave(familiar, unfamiliar, participantId || "anon");
      saveQueue(participantId || "anon", tasks);
      const first = tasks[0];
      const res = await api.createCategorySession(
        first.category, first.familiarity, participantId || undefined,
      );
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
        아래에서 <b>평소 잘 아는 것 {NEED_PER_SIDE}개</b>와{" "}
        <b>잘 모르는 것 {NEED_PER_SIDE}개</b>를 골라 주세요. 고른 순서대로 네 번의 쇼핑을 하게 돼요.
      </p>

      <div className="mt-6 space-y-2">
        {options.map((o) => {
          const picked = picks[o.category];
          return (
            <div
              key={o.category}
              className={`flex items-center gap-3 rounded-xl border p-3 transition-colors ${
                picked ? "border-[#4f46e5] bg-[#f5f5ff]" : "border-[#e4e8eb] bg-white"
              }`}
            >
              <span className="text-2xl" aria-hidden>{o.emoji}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-[#191919]">{o.category}</div>
                {o.blurb && <div className="text-xs text-[#9aa0a6]">{o.blurb}</div>}
              </div>
              <div className="flex shrink-0 gap-1.5">
                {([["familiar", "잘 알아요"], ["unfamiliar", "잘 몰라요"]] as const).map(
                  ([f, label]) => {
                    const on = picked === f;
                    const dim = !on && locked(f);
                    return (
                      <button
                        key={f}
                        onClick={() => choose(o.category, f)}
                        disabled={dim}
                        aria-pressed={on}
                        className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                          on
                            ? "bg-[#4f46e5] text-white"
                            : dim
                              ? "cursor-not-allowed bg-[#f5f6f7] text-[#c4c8cc]"
                              : "border border-[#e4e8eb] bg-white text-[#404040] hover:border-[#4f46e5] hover:text-[#4f46e5]"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  },
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex items-center justify-between gap-4">
        <span className="text-xs text-[#9aa0a6]">
          잘 알아요 {familiar.length}/{NEED_PER_SIDE} · 잘 몰라요 {unfamiliar.length}/{NEED_PER_SIDE}
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
