"use client";

// 발표용 자동 재생 데모 (/demo/replay).
//
// `lib/demoScript.ts`의 비트를 순서대로 적용해 대화를 재생한다. 백엔드 호출이 전혀 없어
// 발표 중 LLM 지연·실패·비결정성이 없고, 렌더는 실제 세션과 같은 컴포넌트를 쓴다.
//
// UI 두 벌을 토글한다:
//   panel  — FS1 참가자가 실제로 본 화면. 좌측 대화 + 우측 440px 패널
//            (이해 패널 + 가치 레이더 + 동기 레이더 + 충돌 카드). **발표 기본값.**
//   inline — 교수님 피드백을 반영한 새 화면. 사이드 패널을 없애고 외재화를 채팅에 인라인.
// 한 화면에서 전환되므로 "FS1에서 쓴 화면 → 이렇게 바꿨다"를 그대로 보여줄 수 있다.
//
// 조작: 재생/일시정지 · 처음부터 · 속도(1x/1.5x/2x) · 한 비트씩(→).
// 키보드: Space=재생/정지, →=다음 비트, R=처음부터, U=UI 전환.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AgentAvatar from "@/components/chat/AgentAvatar";
import ChatComposer from "@/components/chat/ChatComposer";
import MessageBubble from "@/components/chat/MessageBubble";
import ThinkingSkeleton from "@/components/chat/ThinkingSkeleton";
import ProductCard from "@/components/products/ProductCard";
import ProductCarousel from "@/components/products/ProductCarousel";
import ConflictCard from "@/components/preference/ConflictCard";
import CurrentUnderstandingPanel from "@/components/preference/CurrentUnderstandingPanel";
import ConflictUtterance from "@/components/study/ConflictUtterance";
import SequentialCriteriaConfirm from "@/components/study/SequentialCriteriaConfirm";
import {
  BEATS, CHIPS, DEMO_CONFLICT, RESOLUTION,
  buildState, impressionsFor, makeTurn, type Beat,
} from "@/lib/demoScript";
import type { Conflict, Impression, PreferenceChip, PreferenceState, Turn } from "@/lib/types";

const SPEEDS = [1, 1.5, 2] as const;
type UiMode = "panel" | "inline";

type State = {
  turns: Turn[];
  impressions: Record<string, Impression[]>;
  chips: PreferenceChip[];
  scoreKey: string;
  pref: PreferenceState | null;
  thinking: boolean;
  confirmOpen: boolean;
  conflict: Conflict | null;
  finished: boolean;
};

const EMPTY: State = {
  turns: [], impressions: {}, chips: [], scoreKey: "s1", pref: null,
  thinking: false, confirmOpen: false, conflict: null, finished: false,
};

/** 칩·점수가 바뀔 때마다 패널이 쓰는 스냅샷을 다시 만든다 */
const withPref = (s: State, chips: PreferenceChip[], key = s.scoreKey): State => ({
  ...s, chips, scoreKey: key, pref: buildState(chips, key, s.turns.length),
});

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
      const have = new Set(s.chips.map((c) => c.id));
      const next = [...s.chips, ...b.add.filter((c) => !have.has(c.id))];
      return withPref(s, next, b.scores ?? s.scoreKey);
    }
    case "confirm":
      return { ...s, confirmOpen: true };
    case "confirmAnswer": {
      // 위젯은 자체 상태를 갖고 있어 외부에서 '눌린 모습'을 만들 수 없다.
      // 대신 실제 대화처럼 답변 발화를 이어붙여 자동 재생으로도 완결되게 한다.
      const chips = s.chips.map((c) =>
        c.id === CHIPS.multitask.id
          ? { ...c, status: "confirmed", type: "important" as const, confidence: 1 }
          : c);
      const withTurns: State = {
        ...s,
        confirmOpen: false,
        turns: [
          ...s.turns,
          makeTurn(`cu${n}`, "user", "맞아요. 논문이랑 코드를 같이 띄워놓고 보는 편이에요.", n),
          makeTurn(`ca${n + 1}`, "service_agent",
            "반영했어요. 화면을 세로로 넓게 쓰는 게 중요하다고 보고, 앞으로 추천에 그 점을 우선할게요.",
            n + 1, "answer"),
        ],
      };
      return withPref(withTurns, chips);
    }
    case "conflict":
      return { ...s, conflict: DEMO_CONFLICT, thinking: false };
    case "resolve": {
      const rid = `r${n}`;
      const fid = `f${n + 1}`;
      const chips = s.chips.map((c) =>
        c.id === CHIPS.budget.id
          ? { ...c, label: "대기업 중 가격이 낮은 쪽", status: "corrected_by_user", confidence: 1 }
          : c);
      const next: State = {
        ...s,
        conflict: null,
        turns: [
          ...s.turns,
          makeTurn(rid, "service_agent", RESOLUTION.message, n, "resolution"),
          makeTurn(fid, "service_agent", RESOLUTION.followUp, n + 1, "recommend"),
        ],
        impressions: { ...s.impressions, [fid]: impressionsFor(RESOLUTION.set, fid) },
      };
      return withPref(next, chips);
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
  const [ui, setUi] = useState<UiMode>("panel");   // FS1 발표 기본값 = 예전 UI
  const endRef = useRef<HTMLDivElement>(null);

  const step = useCallback(() => {
    setIdx((i) => {
      if (i >= BEATS.length) return i;
      setState((s) => apply(s, BEATS[i]));
      return i + 1;
    });
  }, []);

  const reset = useCallback(() => { setPlaying(false); setIdx(0); setState(EMPTY); }, []);

  useEffect(() => {
    if (!playing || idx >= BEATS.length) return;
    const timer = setTimeout(step, BEATS[idx].ms / speed);
    return () => clearTimeout(timer);
  }, [playing, idx, speed, step]);

  useEffect(() => { if (playing && idx >= BEATS.length) setPlaying(false); }, [playing, idx]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [state.turns.length, state.thinking, state.confirmOpen, state.conflict]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (e.code === "Space") { e.preventDefault(); setPlaying((v) => !v); }
      else if (e.code === "ArrowRight") { e.preventDefault(); setPlaying(false); step(); }
      else if (k === "r") reset();
      else if (k === "u") setUi((m) => (m === "panel" ? "inline" : "panel"));
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

  // ── 대화 본문 (두 UI 공통) ────────────────────────────────────────
  const chatBody = (
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

      {/* 새 UI에서만 — 기준 확인이 채팅 안으로 들어온 게 이 버전의 변경점이다 */}
      {ui === "inline" && state.confirmOpen && (
        <div className="msg-in pl-9">
          <SequentialCriteriaConfirm
            askable={askable} alreadyKnown={known}
            onConfirm={async () => true} onReject={async () => true} onSaveEdit={async () => true}
          />
        </div>
      )}
      {ui === "inline" && state.conflict && (
        <div className="msg-in">
          <ConflictUtterance conflict={state.conflict} onResolve={() => {}} disabled />
        </div>
      )}

      {state.thinking && <ThinkingSkeleton />}
      <div ref={endRef} />
    </div>
  );

  return (
    <div className="mx-auto flex h-[100dvh] max-w-[1200px] flex-col gap-2 p-3 sm:p-4">
      {/* 조작 바 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-xl border border-[#e4e8eb] bg-white px-3 py-2">
        <button
          onClick={() => (idx >= BEATS.length ? reset() : setPlaying((v) => !v))}
          className="btn btn-primary px-4 py-1.5 text-sm"
        >
          {idx >= BEATS.length ? "처음부터" : playing ? "일시정지" : idx === 0 ? "재생" : "이어서 재생"}
        </button>
        <button onClick={() => { setPlaying(false); step(); }} disabled={idx >= BEATS.length}
          className="btn px-3 py-1.5 text-sm disabled:opacity-40">다음</button>
        <button onClick={reset} className="btn px-3 py-1.5 text-sm">리셋</button>

        {/* UI 전환 — 발표에서 before/after를 보여주는 장치 */}
        <div className="ml-3 flex items-center gap-1 rounded-lg bg-[#f4f5f7] p-0.5">
          {([["panel", "예전 UI (패널·그래프)"], ["inline", "새 UI (채팅 인라인)"]] as const).map(
            ([m, label]) => (
              <button
                key={m}
                onClick={() => setUi(m)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                  ui === m ? "bg-white text-[#4f46e5] shadow-sm" : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {label}
              </button>
            ),
          )}
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          {SPEEDS.map((s) => (
            <button key={s} onClick={() => setSpeed(s)}
              className={`rounded-md border px-2 py-1 text-xs font-semibold tabular-nums transition-colors ${
                speed === s ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-500"
              }`}>{s}x</button>
          ))}
        </div>
        <div className="w-full">
          <div className="h-1 w-full overflow-hidden rounded-full bg-[#f0f2f4]">
            <div className="h-full rounded-full bg-[#4f46e5] transition-[width] duration-300"
              style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-[10px] text-slate-400">Space 재생·정지 · → 한 단계 · R 리셋 · U UI 전환</p>
        </div>
      </div>

      {ui === "panel" ? (
        /* ── 예전 UI — FS1 참가자가 본 화면 ── */
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
          <div className="card flex min-h-0 flex-col overflow-hidden">
            {chatBody}
            <div className="border-t border-[#f0f2f4] p-3">
              <ChatComposer onSend={() => {}} disabled placeholder="자동 재생 데모입니다" />
            </div>
          </div>
          <div className="min-h-0 space-y-3 overflow-y-auto pr-1">
            {state.conflict && (
              <ConflictCard conflict={state.conflict} onResolve={() => {}} disabled />
            )}
            <CurrentUnderstandingPanel
              state={state.pref}
              onChipAction={() => {}}
              onShowEvidence={() => {}}
            />
          </div>
        </div>
      ) : (
        /* ── 새 UI — 사이드 패널 없이 채팅 한 컬럼 ── */
        <div className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col">
          <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
            {chatBody}
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
      )}
    </div>
  );
}
