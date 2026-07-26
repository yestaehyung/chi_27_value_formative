"use client";

import { useState } from "react";
import { PreferenceChip, PreferenceState } from "@/lib/types";
import { selectCoreCriteria } from "@/lib/criteria";
import AgentAvatar from "../chat/AgentAvatar";

// 수정안 3 (경량 패널) — CurrentUnderstandingPanel의 포크 (2026-07-16).
// 디자인 언어(카드·타입 배지·버튼 스타일·헤더)는 현재 버전 그대로 유지하고,
// 요소만 뺀다: 레이더 그래프 2종 ✕, 중요도 ⬆⬇ ✕, [수정] ✕.
// 남긴 것: ✓ 맞아요 · ✗ 아니에요 · 근거(EvidenceDrawer — 현재와 동일 동작).
// 더한 것: 우선순위 번호(백엔드 chips 순서 = priority rank + confidence 내림차순),
// 핵심 2~3개만 기본 노출(축 2) + "외 N개 더 보기".

const CHIP_STYLE: Record<string, string> = {
  must_have: "border-[#a7f3d0] bg-[#ecfdf5] text-[#047857]",
  important: "border-[#b3d8ff] bg-[#eaf4ff] text-[#0073e6]",
  nice_to_have: "border-[#e4e8eb] bg-[#f5f6f8] text-[#606060]",
  avoid: "border-[#ffd6d6] bg-[#fff5f5] text-[#e03131]",
  uncertain: "border-dashed border-[#ecc94b] bg-[#fffbe6] text-[#8a6d00]",
};

const CHIP_TYPE_LABEL: Record<string, string> = {
  must_have: "필수", important: "중요", nice_to_have: "선호", avoid: "피하기", uncertain: "불확실",
};

export default function SimpleUnderstandingPanel({
  state,
  onChipAction,
  onShowEvidence,
}: {
  state: PreferenceState | null;
  onChipAction: (topicId: string, action: string) => void;
  onShowEvidence: (topicId: string) => void;
}) {
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [showAll, setShowAll] = useState(false);

  if (!state) {
    return <div className="card p-4 text-sm text-slate-400">아직 파악된 기준이 없어요.</div>;
  }
  const summary = state.userVisibleSummary;
  const chips = summary.chips;
  // 선별은 핵심 2~3개(축 2), 표시 순서·번호는 백엔드 우선순위(chips 원 순서) 그대로.
  const core = selectCoreCriteria(chips);
  const coreOrdered = chips.filter((c) => core.some((k) => k.id === c.id));
  const rest = chips.filter((c) => !core.some((k) => k.id === c.id));
  const rank = (chip: PreferenceChip) => chips.findIndex((c) => c.id === chip.id) + 1;

  const renderChip = (chip: PreferenceChip) => {
    const isConfirmed = confirmed[chip.id] || chip.status === "confirmed";
    return (
      <div key={chip.id} className="rounded-xl border border-[#e8eaed] bg-white px-3 py-2.5">
        {/* 우선순위 번호 + 라벨 + 타입 배지 + 근거 수 (배지·근거수는 현재 버전과 동일) */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 text-xs leading-snug">
            <span className="mr-1.5 font-mono text-[11px] font-bold tabular-nums text-[#4f46e5]">
              {rank(chip)}.
            </span>
            <span
              className={`mr-1.5 inline-block rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${CHIP_STYLE[chip.type] ?? CHIP_STYLE.nice_to_have}`}
            >
              {CHIP_TYPE_LABEL[chip.type]}
            </span>
            <span className="font-medium text-[#191919]" title={chip.displayRationale}>{chip.label}</span>
          </div>
          <span className="shrink-0 text-[10px] tabular-nums text-[#b0b8c1]" title="근거 개수">({chip.evidenceCount})</span>
        </div>

        {/* 맞는지 / 아닌지 — 현재 버전과 동일한 버튼. 중요도/수정은 없음 */}
        <div className="mt-2.5 flex items-center gap-1.5">
          {isConfirmed ? (
            <span className="inline-flex items-center rounded-lg border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
              ✓ 확인됨
            </span>
          ) : (
            <button
              className="btn border-emerald-300 px-2.5 py-1 text-xs text-emerald-700 hover:bg-emerald-50"
              onClick={() => { onChipAction(chip.id, "confirm"); setConfirmed((c) => ({ ...c, [chip.id]: true })); }}
            >
              ✓ 맞아요
            </button>
          )}
          <button
            className="btn border-rose-200 px-2.5 py-1 text-xs text-rose-600 hover:bg-rose-50"
            onClick={() => onChipAction(chip.id, "reject")}
          >
            ✗ 아니에요
          </button>
          <button
            className="ml-auto rounded px-1.5 py-1 text-[11px] text-[#9aa0a6] transition-colors duration-150 hover:text-[#4f46e5] active:scale-[0.96]"
            onClick={() => onShowEvidence(chip.id)}
          >
            근거
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-bold text-[#191919]">
          <AgentAvatar className="h-6 w-6" />
          제가 현재 이렇게 이해했어요
        </h3>
        {summary.needsConfirmation && (
          <span className="rounded-full bg-[#fffbe6] px-2.5 py-1 text-[10px] font-semibold text-[#8a6d00]">
            확인 필요
          </span>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-600">{summary.oneSentenceSummary}</p>

      <div className="mt-3 space-y-2">
        {chips.length === 0 ? (
          <span className="text-xs text-slate-400">대화하면서 기준이 여기에 쌓여요.</span>
        ) : (
          <>
            {coreOrdered.map(renderChip)}
            {showAll && rest.map(renderChip)}
            {rest.length > 0 && !showAll && (
              <button
                onClick={() => setShowAll(true)}
                className="w-full rounded-xl border border-dashed border-[#e4e8eb] px-3 py-2 text-xs text-[#9aa0a6] transition-colors hover:border-[#4f46e5] hover:text-[#4f46e5]"
              >
                외 {rest.length}개 더 보기
              </button>
            )}
          </>
        )}
      </div>

      {(state.hardConstraints.length > 0 || state.avoidances.length > 0) && (
        <div className="mt-3 space-y-1 border-t border-[#f0f2f4] pt-2 text-[11px]">
          {state.hardConstraints.length > 0 && (
            <div className="text-[#047857]">✔ 필수 조건: {state.hardConstraints.join(" · ")}</div>
          )}
          {state.avoidances.length > 0 && (
            <div className="text-[#e03131]">✘ 제외: {state.avoidances.join(" · ")}</div>
          )}
        </div>
      )}
    </div>
  );
}
