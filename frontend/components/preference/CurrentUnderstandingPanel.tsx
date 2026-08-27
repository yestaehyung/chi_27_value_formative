"use client";

import { useState } from "react";
import { PreferenceChip, PreferenceState } from "@/lib/types";
import AnchorRadar from "./AnchorRadar";
import MotivationRadar from "./MotivationRadar";
import AgentAvatar from "../chat/AgentAvatar";
import { OURS_V3, STUDY_UI, tr } from "@/lib/studyI18n";

// 타입별 색 — 타입 배지에 사용
const CHIP_STYLE: Record<string, string> = {
  must_have: "border-[#a7f3d0] bg-[#ecfdf5] text-[#047857]",
  important: "border-[#b3d8ff] bg-[#eaf4ff] text-[#0073e6]",
  nice_to_have: "border-[#e4e8eb] bg-[#f5f6f8] text-[#606060]",
  avoid: "border-[#ffd6d6] bg-[#fff5f5] text-[#e03131]",
  uncertain: "border-dashed border-[#ecc94b] bg-[#fffbe6] text-[#8a6d00]",
};

const CHIP_TYPE_LABEL: Record<string, string> = {
  must_have: tr("필수", "Must have"), important: tr("중요", "Important"), nice_to_have: tr("선호", "Preference"), avoid: tr("피하기", "Avoid"), uncertain: tr("불확실", "Uncertain"),
};

export default function CurrentUnderstandingPanel({
  state,
  onChipAction,
  onShowEvidence,
  showRadar = true,
  editable = true,
}: {
  state: PreferenceState | null;
  onChipAction: (
    topicId: string, action: string, manualLabel?: string
  ) => boolean | void | Promise<boolean | void>;
  onShowEvidence: (topicId: string) => void;
  showRadar?: boolean;
  editable?: boolean;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});

  if (!state) {
    return <div className="card p-4 text-sm text-slate-400">{tr("아직 파악된 기준이 없어요.", "No criteria have been identified yet.")}</div>;
  }
  const summary = state.userVisibleSummary;

  const renderChip = (chip: PreferenceChip) => {
    const isEditing = editing === chip.id;
    const isConfirmed = confirmed[chip.id]
      || chip.status === "confirmed"
      || chip.status === "corrected_by_user";
    const isPending = pending[chip.id] === true;
    const runAction = async (action: string, manualLabel?: string) => {
      if (isPending) return false;
      setPending((p) => ({ ...p, [chip.id]: true }));
      try {
        const result = await onChipAction(chip.id, action, manualLabel);
        return result !== false;
      } finally {
        setPending((p) => ({ ...p, [chip.id]: false }));
      }
    };
    return (
      // msg-in: 새로 파악된 기준만 떠오르며 등장한다 — 기존 칩은 key(chip.id)로 유지되어 재생 안 됨
      <div key={chip.id} className="msg-in rounded-xl border border-[#e8eaed] bg-white px-3 py-2.5">
        {/* 라벨 + 타입 배지 + 근거 수 */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 text-xs leading-snug">
            <span
              className={`mr-1.5 inline-block rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${CHIP_STYLE[chip.type] ?? CHIP_STYLE.nice_to_have}`}
            >
              {CHIP_TYPE_LABEL[chip.type]}
            </span>
            {/* ours-v3: 시스템 추론 가설 칩 구분 — 확인·수정 대상임을 시각화 */}
            {OURS_V3 && chip.status === "inferred" && (
              <span className="mr-1.5 inline-block rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                {STUDY_UI.chat.v3Hypothesis}
              </span>
            )}
            <span className="font-medium text-[#191919]" title={chip.displayRationale}>{chip.label}</span>
          </div>
          <span className="shrink-0 text-[10px] tabular-nums text-[#b0b8c1]" title={tr("근거 개수", "Evidence count")}>({chip.evidenceCount})</span>
        </div>

        {!editable ? null : isEditing ? (
          <div className="mt-2">
            <input
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              autoFocus
              className="w-full rounded-lg border border-[#e4e8eb] px-2 py-1.5 text-xs focus:border-[#4f46e5] focus:outline-none"
              placeholder={tr("기준을 직접 수정하세요", "Edit this criterion")}
            />
            <div className="mt-1.5 flex justify-end gap-1.5">
              <button className="btn px-2.5 py-1 text-[11px]" disabled={isPending} onClick={() => setEditing(null)}>{tr("취소", "Cancel")}</button>
              <button
                className="btn btn-primary px-2.5 py-1 text-[11px]"
                disabled={isPending || !editText.trim()}
                onClick={async () => {
                  if (await runAction("edit_label", editText.trim())) setEditing(null);
                }}
              >
                {tr("저장", "Save")}
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* 맞는지 / 아닌지 — 핵심 correction, 버튼으로 강조 */}
            <div className="mt-2.5 flex items-center gap-1.5">
              {isConfirmed ? (
                <span className="inline-flex items-center rounded-lg border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
                  ✓ {tr("확인됨", "Confirmed")}
                </span>
              ) : (
                <button
                  className="btn border-emerald-300 px-2.5 py-1.5 text-xs text-emerald-700 hover:bg-emerald-50"
                  disabled={isPending}
                  onClick={async () => {
                    if (await runAction("confirm")) {
                      setConfirmed((c) => ({ ...c, [chip.id]: true }));
                    }
                  }}
                >
                  ✓ {tr("맞아요", "Yes")}
                </button>
              )}
              <button
                className="btn border-rose-200 px-2.5 py-1.5 text-xs text-rose-600 hover:bg-rose-50"
                disabled={isPending}
                onClick={() => runAction("reject")}
              >
                ✗ {tr("아니에요", "No")}
              </button>
            </div>

            {/* 보조 — 중요도 / 수정 / 근거. 전부 노출하되 작게/muted 로 위계 구분 */}
            {/* 히트 영역: 작은 텍스트 버튼이지만 패딩으로 터치 타깃을 키운다 (서로 인접해
                40px 정사각은 겹치므로, 충돌 없는 한도까지). scale은 transition 대상에 포함
                — 없으면 눌림이 뚝 끊긴다. */}
            <div className="-mb-1 mt-1.5 flex flex-wrap items-center gap-x-1 gap-y-1 text-[11px] text-[#9aa0a6]">
              <span className="flex items-center gap-0.5">
                {tr("중요도", "Priority")}
                <button disabled={isPending} className="rounded-md px-2 py-1.5 transition-[color,background-color,scale] duration-150 hover:bg-[#f0f2f4] hover:text-[#4f46e5] active:scale-[0.96]" title={tr("중요도 낮춤", "Decrease priority")} onClick={() => runAction("decrease_priority")}>⬇</button>
                <button disabled={isPending} className="rounded-md px-2 py-1.5 transition-[color,background-color,scale] duration-150 hover:bg-[#f0f2f4] hover:text-[#4f46e5] active:scale-[0.96]" title={tr("중요도 높임", "Increase priority")} onClick={() => runAction("increase_priority")}>⬆</button>
              </span>
              <button disabled={isPending} className="rounded-md px-2 py-1.5 transition-[color,scale] duration-150 hover:text-[#4f46e5] active:scale-[0.96]" onClick={() => { setEditing(chip.id); setEditText(chip.label); }}>{tr("수정", "Edit")}</button>
              <button className="rounded-md px-2 py-1.5 transition-[color,scale] duration-150 hover:text-[#4f46e5] active:scale-[0.96]" data-tutorial="evidence" onClick={() => onShowEvidence(chip.id)}>{tr("근거", "Evidence")}</button>
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
          {tr("제가 현재 이렇게 이해했어요", "Here Is What I Currently Understand")}
        </h3>
        {summary.needsConfirmation && (
          <span className="rounded-full bg-[#fffbe6] px-2.5 py-1 text-[10px] font-semibold text-[#8a6d00]">
            {tr("확인 필요", "Needs confirmation")}
          </span>
        )}
      </div>

      <p className="mt-2 text-xs leading-relaxed text-slate-600">{summary.oneSentenceSummary}</p>

      <div className="mt-3 space-y-2" data-tutorial="criteria">
        {summary.chips.length === 0 ? (
          <span className="text-xs text-slate-400">{tr("대화하면서 기준이 여기에 쌓여요.", "Criteria identified during the conversation will appear here.")}</span>
        ) : (
          summary.chips.map(renderChip)
        )}
      </div>

      {(state.hardConstraints.length > 0 || state.avoidances.length > 0) && (
        <div className="mt-3 space-y-1 border-t border-[#f0f2f4] pt-2 text-[11px]">
          {state.hardConstraints.length > 0 && (
            <div className="text-[#047857]">✔ {tr("필수 조건", "Must-have requirements")}: {state.hardConstraints.join(" · ")}</div>
          )}
          {state.avoidances.length > 0 && (
            <div className="text-[#e03131]">✘ {tr("제외", "Avoid")}: {state.avoidances.join(" · ")}</div>
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
            <MotivationRadar
              scores={state.motivationScores || {}}
              evidence={state.motivationEvidence}
              size={260}
            />
          </div>
        )}
      </div>
    </div>
  );
}
