"use client";

// 순차 기준 확인 (안 E, 2026-07-21) — Claude Code의 AskUserQuestion 패턴을 옮긴 것.
// 원리: 재인>재생, 갈림길에서만 묻기, 막히지 않는 탈출구.
//  · 확실한 기준(alreadyKnown)은 심문하지 않고 "이미 반영해뒀어요"로 알려만 준다.
//  · 애매한 기준(askable, 보통 1~2개)만 한 개씩 발화로 확인 — 답하면 다음이 뜬다.
//  · 달라요 → 기존 라벨이 채워진 인라인 수정(재인·빠름) + "직접 말씀할게요" 탈출구(대화).
// 표면은 MessageBubble 에이전트 턴과 동일(아바타+역할 라벨+버블). 질문 목록은 mount 시
// 고정(확인/거부로 서버 상태가 바뀌어도 진행 중 목록이 흔들리지 않게).

import { useEffect, useState } from "react";
import { PreferenceChip } from "@/lib/types";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ChipTypeBadge from "@/components/preference/ChipTypeBadge";

type Answer = { kind: "confirmed" | "edited" | "handoff"; label?: string };

export default function SequentialCriteriaConfirm({
  askable,
  alreadyKnown = [],
  onConfirm,
  onReject,
  onSaveEdit,
  onEscapeToChat,
  onComplete,
  disabled,
}: {
  askable: PreferenceChip[];
  alreadyKnown?: PreferenceChip[];
  onConfirm: (id: string) => Promise<boolean>;
  onReject: (id: string) => Promise<boolean>;
  onSaveEdit: (id: string, label: string) => Promise<boolean>;
  onEscapeToChat?: (chip: PreferenceChip) => void;
  onComplete?: () => void; // 마지막 질문까지 처리되면 1회 호출 (후속 대화 트리거용)
  disabled?: boolean;
}) {
  const [items] = useState(() => askable); // mount 시 고정
  const [known] = useState(() => alreadyKnown);
  const [answered, setAnswered] = useState<Record<string, Answer>>({});
  const [idx, setIdx] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [busy, setBusy] = useState(false);

  const current = items[idx];
  const done = idx >= items.length;
  const hasHistory = known.length > 0 || Object.keys(answered).length > 0;

  useEffect(() => {
    if (done) onComplete?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  const advance = () => { setIdx((i) => i + 1); setEditing(false); setEditText(""); };

  const confirm = async () => {
    if (!current || busy) return;
    setBusy(true);
    const ok = await onConfirm(current.id);
    setBusy(false);
    if (ok) { setAnswered((a) => ({ ...a, [current.id]: { kind: "confirmed" } })); advance(); }
  };

  const startReject = async () => {
    if (!current || busy) return;
    setBusy(true);
    const ok = await onReject(current.id);
    setBusy(false);
    if (ok) { setEditing(true); setEditText(current.label); }
  };

  const saveEdit = async () => {
    if (!current || busy || !editText.trim()) return;
    setBusy(true);
    const ok = await onSaveEdit(current.id, editText.trim());
    setBusy(false);
    if (ok) { setAnswered((a) => ({ ...a, [current.id]: { kind: "edited", label: editText.trim() } })); advance(); }
  };

  const escapeToChat = () => {
    if (!current) return;
    setAnswered((a) => ({ ...a, [current.id]: { kind: "handoff" } }));
    onEscapeToChat?.(current);
    advance();
  };

  return (
    <div className="flex gap-2.5">
      <AgentAvatar className="mt-1 h-7 w-7" />
      {/* 모바일: 남은 폭 전부, sm 이상에서만 85% 상한 */}
      <div className="min-w-0 flex-1 sm:max-w-[85%]">
        <div className="mb-1 flex items-center gap-2 text-[11px] text-[#9aa0a6]">
          <span className="font-medium text-[#404040]">쇼핑 에이전트</span>
          <span className="rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-medium text-[#4f46e5]">기준 확인</span>
        </div>
        <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3">
          {/* 명시적으로 말씀하신 기준 — 심문하지 않고 반영했음만 알림 (갈림길에서만 묻는다).
              '여러 번' 같은 빈도 표현은 쓰지 않는다(한 번 말한 것도 반영되므로 오해 소지). */}
          {known.length > 0 && (
            <p className="text-pretty text-sm leading-[1.7] text-[#191919]">
              말씀해주신 {known.map((c) => `‘${c.label}’`).join(", ")}은(는) 반영해뒀어요.
              {items.length > 0 && " 몇 가지만 더 확인할게요."}
            </p>
          )}

          {/* 답한 기준 — 쌓이는 대화 로그 */}
          {Object.keys(answered).length > 0 && (
            <div className={`space-y-1 ${known.length ? "mt-2.5 border-t border-[#f0f2f4] pt-2.5" : ""}`}>
              {items.filter((c) => answered[c.id]).map((c) => {
                const a = answered[c.id];
                return (
                  <div key={c.id} className="flex items-start gap-1.5 text-[12px] leading-snug">
                    <span className={`shrink-0 font-semibold ${a.kind === "confirmed" ? "text-emerald-700" : a.kind === "edited" ? "text-[#4f46e5]" : "text-[#9aa0a6]"}`}>
                      {a.kind === "confirmed" ? "✓" : a.kind === "edited" ? "✎" : "↩"}
                    </span>
                    <span className="text-[#404040]">
                      {a.kind === "edited" ? <>{c.label} → <b className="font-semibold text-[#191919]">{a.label}</b></>
                        : a.kind === "handoff" ? <>{c.label} — 대화로 말씀하기로</>
                          : c.label}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* 현재 질문 (한 개씩) 또는 완료 */}
          {!done ? (
            <div className={hasHistory ? "mt-3" : ""}>
              {!editing ? (
                <>
                  {/* 극성 중립 질문 — 원하는 것/피할 것 판단을 프론트가 하드코딩하지 않는다.
                      극성은 [피하기]/[중요] 배지(데이터 기반)가 담당. 라벨이 부정형이어도
                      이중 부정("안 겹치는 것을 피하고 싶으신") 오문이 생기지 않는다. */}
                  <div className="flex items-center gap-2">
                    <ChipTypeBadge type={current.type} />
                    <p className="text-pretty text-sm text-[#191919]">
                      ‘{current.label}’, 이렇게 이해했는데 맞을까요?
                    </p>
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    <button
                      disabled={disabled || busy}
                      onClick={confirm}
                      className="btn border-emerald-300 px-3 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50"
                    >
                      네, 맞아요
                    </button>
                    <button
                      disabled={disabled || busy}
                      onClick={startReject}
                      className="btn border-rose-200 px-3 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
                    >
                      아니에요, 달라요
                    </button>
                  </div>
                </>
              ) : (
                <div>
                  <p className="text-[12px] text-[#9aa0a6]">그럼 어떻게 볼까요? 고쳐서 알려주세요.</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <input
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      autoFocus
                      className="min-w-0 flex-1 basis-40 rounded-lg border border-[#e4e8eb] px-2 py-1.5 text-xs focus:border-[#4f46e5] focus:outline-none"
                    />
                    <button disabled={busy || !editText.trim()} onClick={saveEdit} className="btn btn-primary px-2.5 py-1.5 text-xs">
                      저장
                    </button>
                  </div>
                  <button onClick={escapeToChat} className="mt-1.5 text-[11px] text-[#9aa0a6] transition-colors hover:text-[#4f46e5]">
                    직접 말씀할게요 →
                  </button>
                </div>
              )}
            </div>
          ) : (
            <p className={`text-pretty text-sm leading-[1.7] text-[#191919] ${hasHistory ? "mt-3" : ""}`}>
              확인 고마워요 — 이 기준들로 다시 골라볼게요.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
