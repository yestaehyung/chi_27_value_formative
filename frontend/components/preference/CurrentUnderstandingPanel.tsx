"use client";

import { useState } from "react";
import { PreferenceChip, PreferenceState } from "@/lib/types";
import AnchorRadar from "./AnchorRadar";
import MotivationRadar from "./MotivationRadar";
import AgentAvatar from "../chat/AgentAvatar";

// 타입별 색 — 타입 배지에 사용
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

export default function CurrentUnderstandingPanel({
  state,
  onChipAction,
  onShowEvidence,
  showRadar = true,
  editable = true,
}: {
  state: PreferenceState | null;
  onChipAction: (topicId: string, action: string, manualLabel?: string) => void;
  onShowEvidence: (topicId: string) => void;
  showRadar?: boolean;
  editable?: boolean;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});

  if (!state) {
    return <div className="card p-4 text-sm text-slate-400">아직 파악된 기준이 없어요.</div>;
  }
  const summary = state.userVisibleSummary;

  const renderChip = (chip: PreferenceChip) => {
    const isEditing = editing === chip.id;
    const isConfirmed = confirmed[chip.id];
    return (
      <div key={chip.id} className="rounded-xl border border-[#e8eaed] bg-white px-3 py-2.5">
        {/* 라벨 + 타입 배지 + 근거 수 */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 text-xs leading-snug">
            <span
              className={`mr-1.5 inline-block rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${CHIP_STYLE[chip.type] ?? CHIP_STYLE.nice_to_have}`}
            >
              {CHIP_TYPE_LABEL[chip.type]}
            </span>
            <span className="font-medium text-[#191919]" title={chip.displayRationale}>{chip.label}</span>
          </div>
          <span className="shrink-0 text-[10px] tabular-nums text-[#b0b8c1]" title="근거 개수">({chip.evidenceCount})</span>
        </div>

        {!editable ? null : isEditing ? (
          <div className="mt-2">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              autoFocus
              className="w-full rounded-lg border border-[#e4e8eb] px-2 py-1.5 text-xs focus:border-[#4f46e5] focus:outline-none"
              placeholder="기준을 직접 수정하세요"
            />
            <div className="mt-1.5 flex justify-end gap-1.5">
              <button className="btn px-2.5 py-1 text-[11px]" onClick={() => setEditing(null)}>취소</button>
              <button
                className="btn btn-primary px-2.5 py-1 text-[11px]"
                onClick={() => { onChipAction(chip.id, "edit_label", editText); setEditing(null); }}
              >
                저장
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* 맞는지 / 아닌지 — 핵심 correction, 버튼으로 강조 */}
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
            </div>

            {/* 보조 — 중요도 / 수정 / 근거. 전부 노출하되 작게/muted 로 위계 구분 */}
            <div className="-mb-1 mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-[#9aa0a6]">
              <span className="flex items-center gap-0.5">
                중요도
                <button className="rounded px-1.5 py-1 transition-colors duration-150 hover:bg-[#f0f2f4] hover:text-[#4f46e5] active:scale-[0.9]" title="중요도 낮춤" onClick={() => onChipAction(chip.id, "decrease_priority")}>⬇</button>
                <button className="rounded px-1.5 py-1 transition-colors duration-150 hover:bg-[#f0f2f4] hover:text-[#4f46e5] active:scale-[0.9]" title="중요도 높임" onClick={() => onChipAction(chip.id, "increase_priority")}>⬆</button>
              </span>
              <button className="rounded px-1.5 py-1 transition-colors duration-150 hover:text-[#4f46e5] active:scale-[0.96]" onClick={() => { setEditing(chip.id); setEditText(chip.label); }}>수정</button>
              <button className="rounded px-1.5 py-1 transition-colors duration-150 hover:text-[#4f46e5] active:scale-[0.96]" data-tutorial="evidence" onClick={() => onShowEvidence(chip.id)}>근거</button>
            </div>
          </>
        )}
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

      <div className="mt-3 space-y-2" data-tutorial="criteria">
        {summary.chips.length === 0 ? (
          <span className="text-xs text-slate-400">대화하면서 기준이 여기에 쌓여요.</span>
        ) : (
          summary.chips.map(renderChip)
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

      <div data-tutorial="radars">
        {showRadar && (
          <div className="mt-3 border-t border-[#f0f2f4] pt-3">
            <div className="mb-5 text-center text-[11px] font-medium text-[#9aa0a6]">
              가치 분포
            </div>
            <AnchorRadar scores={state.anchorScores} breakdown={state.anchorBreakdown} size={260} />
          </div>
        )}

        {showRadar && (
          <div className="mt-3 border-t border-[#f0f2f4] pt-3">
            <div className="mb-5 text-center text-[11px] font-medium text-[#9aa0a6]">
              이번 쇼핑 동기
            </div>
            <MotivationRadar scores={state.motivationScores || {}} size={260} />
          </div>
        )}
      </div>
    </div>
  );
}
