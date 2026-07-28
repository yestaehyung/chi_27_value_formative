"use client";

// 발표용 자동 재생 데모 (/demo/replay).
//
// `lib/demoScript.ts`의 비트를 순서대로 적용해 대화를 재생한다. 백엔드 호출이 전혀 없어
// 발표 중 LLM 지연·실패·비결정성이 없고, 렌더는 실제 세션과 같은 컴포넌트를 쓴다.
//
// 조작: 재생/일시정지 · 처음부터 · 속도(1x/1.5x/2x) · 한 비트씩 넘기기(→).
// 키보드: Space=재생/정지, →=다음 비트, R=처음부터.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AgentAvatar from "@/components/chat/AgentAvatar";
import ChatComposer from "@/components/chat/ChatComposer";
import MessageBubble from "@/components/chat/MessageBubble";
import ThinkingSkeleton from "@/components/chat/ThinkingSkeleton";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ConflictUtterance from "@/components/study/ConflictUtterance";
import SequentialCriteriaConfirm from "@/components/study/SequentialCriteriaConfirm";
import {
  BEATS, CHIPS, DEMO_CONFLICT, RESOLUTION,
  impressionsFor, makeTurn, type Beat,
} from "@/lib/demoScript";
import type { Conflict, Impression, PreferenceChip, Turn } from "@/lib/types";

const SPEEDS = [1, 1.5, 2] as const;

type State = {
  turns: Turn[];
  impressions: Record<string, Impression[]>;
  chips: PreferenceChip[];
  thinking: boolean;
  confirmOpen: boolean;
  confirmDone: boolean;
  conflict: Conflict | null;
  finished: boolean;
};

const EMPTY: State = {
  turns: [], impressions: {}, chips: [], thinking: false,
  confirmOpen: false, confirmDone: false, conflict: null, finished: false,
};

/** 비트 하나를 상태에 적용 — 순수 함수라 되감기·건너뛰기가 안전하다 */
function apply(s: State, b: Beat): State {
  const n = s.turns.length;
  switch (b.t) {
    case "user":
      return { ...s, turns: [...s.turns, makeTurn(`u${n}`, "user", b.text, n)], thinking: false };
    case "thinking":
      return { ...s, thinking: true };
    case "agent": {
      const id = `a${n}`;
      const turn = makeTurn(id, "service_agent", b.text, n, b.action);
      const imps = b.set ? { ...s.impressions, [id]: impressionsFor(b.set, id) } : s.impressions;
      return { ...s, turns: [...s.turns, turn], impressions: imps, thinking: false };
    }
    case "chips": {
      const ids = new Set(s.chips.map((c) => c.id));
      return { ...s, chips: [...s.chips, ...b.add.filter((c) => !ids.has(c.id))] };
    }
    case "confirm":
      return { ...s, confirmOpen: true };
    case "confirmAnswer":
      // 위젯은 자체 상태를 갖고 있어 외부에서 '눌린 모습'을 만들 수 없다.
      // 대신 실제 대화처럼 답변 발화를 이어붙여 자동 재생으로도 완결되게 한다.
      return {
        ...s,
        confirmOpen: false,
        confirmDone: true,
        turns: [
          ...s.turns,
          makeTurn(`cu${n}`, "user", "맞아요. 논문이랑 코드를 같이 띄워놓고 보는 편이에요.", n),
          makeTurn(`ca${n + 1}`, "service_agent",
            "반영했어요. 화면을 세로로 넓게 쓰는 게 중요하다고 보고, 앞으로 추천에 그 점을 우선할게요.",
            n + 1, "answer"),
        ],
        // 추론이던 기준이 사용자 확인으로 승격된다
        chips: s.chips.map((c) =>
          c.id === CHIPS.multitask.id
            ? { ...c, status: "confirmed", type: "important", confidence: 1 }
            : c),
      };
    case "conflict":
      return { ...s, conflict: DEMO_CONFLICT, thinking: false };
    case "resolve": {
      const rid = `r${n}`;
      const fid = `f${n + 1}`;
      return {
        ...s,
        conflict: null,
        turns: [
          ...s.turns,
          makeTurn(rid, "service_agent", RESOLUTION.message, n, "resolution"),
          makeTurn(fid, "service_agent", RESOLUTION.followUp, n + 1, "recommend"),
        ],
        impressions: { ...s.impressions, [fid]: impressionsFor(RESOLUTION.set, fid) },
        chips: s.chips.map((c) =>
          c.id === CHIPS.budget.id
            ? { ...c, label: "대기업 중 가격이 낮은 쪽", status: "corrected_by_user", confidence: 1 }
            : c),
      };
    }
    case "end":
      return { ...s, finished: true };
  }
}

export default function DemoReplayPage() {
  const [idx, setIdx] = useState(0);          // 다음에 적용할 비트
  const [state, setState] = useState<State>(EMPTY);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);
  const endRef = useRef<HTMLDivElement>(null);

  const step = useCallback(() => {
    setIdx((i) => {
      if (i >= BEATS.length) return i;
      setState((s) => apply(s, BEATS[i]));
      return i + 1;
    });
  }, []);

  const reset = useCallback(() => {
    setPlaying(false);
    setIdx(0);
    setState(EMPTY);
  }, []);

  // 자동 재생 — 각 비트의 ms만큼 기다렸다 다음으로
  useEffect(() => {
    if (!playing || idx >= BEATS.length) return;
    const wait = BEATS[idx].ms / speed;
    const timer = setTimeout(step, wait);
    return () => clearTimeout(timer);
  }, [playing, idx, speed, step]);

  useEffect(() => {
    if (playing && idx >= BEATS.length) setPlaying(false);
  }, [playing, idx]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns.length, state.thinking, state.confirmOpen, state.conflict]);

  // 키보드 조작 — 발표 중 클릭 없이 진행
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Space") { e.preventDefault(); setPlaying((v) => !v); }
      else if (e.code === "ArrowRight") { e.preventDefault(); setPlaying(false); step(); }
      else if (e.key.toLowerCase() === "r") reset();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, reset]);

  const progress = Math.round((idx / BEATS.length) * 100);
  const core = useMemo(() => state.chips.slice(0, 4), [state.chips]);
  const askable = useMemo(() => [CHIPS.multitask], []);
  const known = useMemo(
    () => state.chips.filter((c) => c.status === "confirmed" && c.id !== CHIPS.multitask.id).slice(0, 3),
    [state.chips],
  );

  return (
    <div className="mx-auto flex h-[100dvh] max-w-3xl flex-col gap-2 p-3 sm:p-4">
      {/* 조작 바 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-xl border border-[#e4e8eb] bg-white px-3 py-2">
        <button
          onClick={() => (idx >= BEATS.length ? reset() : setPlaying((v) => !v))}
          className="btn btn-primary px-4 py-1.5 text-sm"
        >
          {idx >= BEATS.length ? "처음부터" : playing ? "일시정지" : idx === 0 ? "재생" : "이어서 재생"}
        </button>
        <button onClick={() => { setPlaying(false); step(); }} disabled={idx >= BEATS.length}
          className="btn px-3 py-1.5 text-sm disabled:opacity-40">
          다음
        </button>
        <button onClick={reset} className="btn px-3 py-1.5 text-sm">리셋</button>

        <div className="ml-auto flex items-center gap-1.5">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`rounded-md border px-2 py-1 text-xs font-semibold tabular-nums transition-colors ${
                speed === s ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-500"
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
        <div className="w-full">
          <div className="h-1 w-full overflow-hidden rounded-full bg-[#f0f2f4]">
            <div className="h-full rounded-full bg-[#4f46e5] transition-[width] duration-300"
              style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-[10px] text-slate-400">
            Space 재생·정지 · → 한 단계 · R 리셋
          </p>
        </div>
      </div>

      {/* 대화 — 실제 세션과 같은 컴포넌트 */}
      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {state.turns.length === 0 && !state.thinking && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <AgentAvatar className="h-12 w-12" />
              <p className="mt-3 text-sm text-slate-400">재생을 누르면 대화가 시작됩니다.</p>
            </div>
          )}

          {state.turns.map((t) => (
            <div key={t.id} className="msg-in space-y-3">
              <MessageBubble turn={t} />
              {state.impressions[t.id] && (
                <div className="pl-9">
                  <ProductCarousel>
                    {state.impressions[t.id].map((imp, i) => (
                      <ProductCard key={imp.id} impression={imp} index={i}
                        givenFeedback={[]} onFeedback={() => {}} disabled />
                    ))}
                  </ProductCarousel>
                </div>
              )}
            </div>
          ))}

          {state.confirmOpen && (
            <div className="msg-in pl-9">
              {/* 발표자가 직접 눌러도 되고(라이브 느낌), 그냥 두면 다음 비트가 답변을 이어붙인다 */}
              <SequentialCriteriaConfirm
                askable={askable}
                alreadyKnown={known}
                onConfirm={async () => true}
                onReject={async () => true}
                onSaveEdit={async () => true}
              />
            </div>
          )}

          {state.conflict && (
            <div className="msg-in">
              <ConflictUtterance conflict={state.conflict} onResolve={() => {}} disabled />
            </div>
          )}

          {state.thinking && <ThinkingSkeleton />}
          <div ref={endRef} />
        </div>

        {/* 입력창 위 앵커 — 기준이 쌓이는 걸 보여주는 곳 */}
        {core.length > 0 && (
          <div className="border-t border-[#f0f2f4] bg-[#fafbfc] px-5 py-2">
            <div className="flex w-full items-center gap-1.5 text-left text-xs text-[#5f6368]">
              <span className="shrink-0 font-semibold text-[#9aa0a6]">이해한 기준:</span>
              <span className="min-w-0 flex-1 truncate font-medium text-[#191919]">
                {core.map((c) => (c.status === "confirmed" ? "✓ " : "") + c.label).join(" · ")}
              </span>
              {state.chips.length > core.length && (
                <span className="shrink-0 text-[#9aa0a6]">외 {state.chips.length - core.length}개</span>
              )}
            </div>
          </div>
        )}

        <div className="border-t border-[#f0f2f4] p-3">
          <ChatComposer onSend={() => {}} disabled placeholder="자동 재생 데모입니다" />
        </div>
      </div>
    </div>
  );
}
