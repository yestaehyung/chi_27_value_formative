"use client";

// 기준 확인 위젯 (안 D·E 공용, 2026-07-21) — 채팅 디자인 언어에 맞춘 리디자인.
// MessageBubble 에이전트 버블(흰 배경 + #e4e8eb 테두리 + rounded-2xl)과 동일한 표면,
// 버튼은 CurrentUnderstandingPanel의 ✓맞아요/✗아니에요와 동일한 .btn 스타일.
//
// presentation "inline"  — 안 D: 추천 아래 붙는 확인 카드 (라벨 "이해 확인")
// presentation "question" — 안 E: 아바타 + 역할 라벨이 붙는 독립 질문 턴
//
// 상태는 위젯이 소유한다: 달라요 → onReject 즉시 호출(서버 반영) + 인라인 수정 열림.
// reject되어 chips에서 사라진 칩은 held로 잡아 수정이 끝날 때까지 행을 유지한다.
// 취소해도 reject는 이미 반영된 상태로 남는다(의도된 동작 — "달라요"는 사실 신호).

import { useEffect, useRef, useState } from "react";
import { PreferenceChip } from "@/lib/types";
import { understandingSentence } from "@/lib/criteria";
import AgentAvatar from "@/components/chat/AgentAvatar";
import ChipTypeBadge from "@/components/preference/ChipTypeBadge";

export default function CriteriaConfirmWidget({
  chips,
  presentation,
  onConfirm,
  onReject,
  onSaveEdit,
  disabled,
  initialEditingId,
}: {
  chips: PreferenceChip[];
  presentation: "inline" | "question";
  onConfirm: (topicId: string) => Promise<boolean>;
  onReject: (topicId: string) => Promise<boolean>;
  onSaveEdit: (topicId: string, label: string) => Promise<boolean>;
  disabled?: boolean;
  initialEditingId?: string; // 데모 프리셋용 — 처음부터 수정 진행 중 상태로
}) {
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [held, setHeld] = useState<PreferenceChip | null>(null); // 수정 중인 칩 (reject 후에도 행 유지)
  const [editText, setEditText] = useState("");
  const [editReady, setEditReady] = useState(false); // reject 서버 반영 후에만 저장 허용
  const inFlight = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (!initialEditingId) return;
    const chip = chips.find((c) => c.id === initialEditingId);
    if (chip) {
      setHeld(chip);
      setEditText(chip.label);
      setEditReady(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rows = held && !chips.some((c) => c.id === held.id) ? [...chips, held] : chips;

  const run = async (id: string, fn: () => Promise<boolean>) => {
    if (inFlight.current.has(id)) return false;
    inFlight.current.add(id);
    setPending((p) => ({ ...p, [id]: true }));
    try {
      return await fn();
    } finally {
      inFlight.current.delete(id);
      setPending((p) => ({ ...p, [id]: false }));
    }
  };

  const startCorrection = (chip: PreferenceChip) => {
    if (held) return;
    setHeld(chip);
    setEditText(chip.label);
    setEditReady(false);
    run(chip.id, () => onReject(chip.id)).then((ok) => {
      if (ok) setEditReady(true);
      else setHeld(null);
    });
  };

  const save = async () => {
    if (!held || !editText.trim()) return;
    const ok = await run(held.id, () => onSaveEdit(held.id, editText.trim()));
    if (ok) setHeld(null);
  };

  // 행: [타입 배지 + 라벨] / [버튼들]. flex-wrap — 좁은 화면(모바일)에서는 버튼이
  // 라벨 아래 줄로 내려간다. 타입은 색+텍스트 배지로 자기설명 (색상 단독 인코딩 금지).
  const renderRow = (chip: PreferenceChip) => {
    const confirmed = chip.status === "confirmed";
    const editing = held?.id === chip.id;
    const busy = pending[chip.id];
    return (
      <div key={chip.id} className="flex flex-wrap items-center gap-x-2 gap-y-1.5 py-1">
        <ChipTypeBadge type={chip.type} />
        <span className="min-w-0 flex-1 basis-36 break-words text-[13px] font-medium text-[#191919]">
          {chip.label}
        </span>
        {editing ? (
          <div className="flex w-full flex-wrap items-center justify-end gap-1.5">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              autoFocus
              className="min-w-0 flex-1 basis-36 rounded-lg border border-[#e4e8eb] px-2 py-1.5 text-xs focus:border-[#4f46e5] focus:outline-none"
            />
            {/* 주의: 취소해도 '달라요'(reject)는 이미 반영된 상태 */}
            <button className="btn px-2.5 py-1 text-xs" disabled={busy} onClick={() => setHeld(null)}>
              취소
            </button>
            <button
              className="btn btn-primary px-2.5 py-1 text-xs"
              disabled={busy || !editReady || !editText.trim()}
              onClick={save}
            >
              저장
            </button>
          </div>
        ) : confirmed ? (
          <span className="ml-auto inline-flex items-center rounded-lg border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
            ✓ 확인됨
          </span>
        ) : (
          <div className="ml-auto flex items-center gap-1.5">
            <button
              className="btn border-emerald-300 px-2.5 py-1 text-xs text-emerald-700 hover:bg-emerald-50"
              disabled={disabled || busy || held !== null}
              onClick={() => run(chip.id, () => onConfirm(chip.id))}
            >
              ✓ 맞아요
            </button>
            <button
              className="btn border-rose-200 px-2.5 py-1 text-xs text-rose-600 hover:bg-rose-50"
              disabled={disabled || busy || held !== null}
              onClick={() => startCorrection(chip)}
            >
              ✗ 달라요
            </button>
          </div>
        )}
      </div>
    );
  };

  const bubble = (
    <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3">
      {presentation === "inline" && (
        <div className="mb-1 text-[11px] font-medium text-[#9aa0a6]">이해 확인</div>
      )}
      <p className="text-pretty text-sm leading-[1.7] text-[#191919]">{understandingSentence(chips)}</p>
      <div className="mt-2.5 space-y-1.5 border-t border-[#f0f2f4] pt-2.5">{rows.map(renderRow)}</div>
    </div>
  );

  if (presentation === "question") {
    // 안 E — MessageBubble 에이전트 턴과 동일한 해부: 아바타 + 역할 라벨 + 버블
    return (
      <div className="flex gap-2.5">
        <AgentAvatar className="mt-1 h-7 w-7" />
        {/* 모바일: 남은 폭 전부 사용, sm 이상에서만 MessageBubble과 같은 85% 상한 */}
        <div className="min-w-0 flex-1 sm:max-w-[85%]">
          <div className="mb-1 flex items-center gap-2 text-[11px] text-[#9aa0a6]">
            <span className="font-medium text-[#404040]">쇼핑 에이전트</span>
            <span className="rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-medium text-[#4f46e5]">
              기준 확인
            </span>
          </div>
          {bubble}
        </div>
      </div>
    );
  }

  return <div className="max-w-full sm:max-w-[85%]">{bubble}</div>;
}
