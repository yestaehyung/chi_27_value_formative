"use client";

// 충돌 발화 (안 E 전용, 2026-07-21) — ConflictCard 대신 에이전트 발화 형식.
// 팀원 피드백(2026-07-21): 발화 틀은 좋으나 정보가 줄었다 →
// ConflictCard의 두 정보를 버블 안으로 되살림:
//  (1) [지금까지 이해 ↔ 방금 보인 것] 대비 (oldAssumption/newSignal)
//  (2) 각 선택지의 결과 미리보기(resultingStatePreview) — 카드는 hover, 여기선 항상 노출
// 표면은 MessageBubble 에이전트 턴과 동일(아바타+역할 라벨+버블). manual_edit 옵션은
// 제외하고 "직접 말씀해 주세요"로 대화 경로로 돌린다.

import { Conflict } from "@/lib/types";
import AgentAvatar from "@/components/chat/AgentAvatar";

export default function ConflictUtterance({
  conflict,
  onResolve,
  disabled,
}: {
  conflict: Conflict;
  onResolve: (optionId: string) => void;
  disabled?: boolean;
}) {
  const options = conflict.suggestedResolutions?.filter((o) => o.action !== "manual_edit") ?? [];
  return (
    <div className="flex gap-2.5">
      <AgentAvatar className="mt-1 h-7 w-7" />
      {/* 모바일: 남은 폭 전부 사용, sm 이상에서만 85% 상한 */}
      <div className="min-w-0 flex-1 sm:max-w-[85%]">
        <div className="mb-1 flex items-center gap-2 text-[11px] text-[#9aa0a6]">
          <span className="font-medium text-[#404040]">쇼핑 에이전트</span>
          <span className="rounded bg-[#fffbe6] px-1.5 py-0.5 text-[10px] font-medium text-[#8a6d00]">
            기준 충돌
          </span>
        </div>
        <div className="rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3">
          <p className="text-pretty text-sm leading-[1.7] text-[#191919]">
            {conflict.explanationForUser || "기준이 바뀐 것 같아요. 어떻게 반영할까요?"}
          </p>

          {/* (1) 지금까지 이해 ↔ 방금 보인 것 — 카드의 대비표를 발화 톤에 맞춰 경량화 */}
          {(conflict.oldAssumption || conflict.newSignal) && (
            <div className="mt-2.5 space-y-1 rounded-xl bg-[#f9fafb] px-3 py-2 text-[12px] leading-snug">
              {conflict.oldAssumption && (
                <div className="flex gap-1.5">
                  <span className="shrink-0 font-semibold text-[#9aa0a6]">지금까지</span>
                  <span className="text-[#404040]">{conflict.oldAssumption}</span>
                </div>
              )}
              {conflict.newSignal && (
                <div className="flex gap-1.5">
                  <span className="shrink-0 font-semibold text-[#4f46e5]">방금</span>
                  <span className="text-[#404040]">{conflict.newSignal}</span>
                </div>
              )}
            </div>
          )}

          {/* (2) 선택지 — 결과 미리보기를 각 옵션 아래 항상 노출 (카드의 hover 미리보기 대체) */}
          <div className="mt-2.5 space-y-1.5">
            {options.map((o) => (
              <button
                key={o.id}
                disabled={disabled}
                onClick={() => onResolve(o.id)}
                className="block w-full rounded-xl border border-[#e4e8eb] bg-white px-3.5 py-2.5 text-left transition-[color,background-color,border-color,transform] duration-150 hover:border-[#4f46e5] hover:bg-[#f5f7ff] active:scale-[0.98] disabled:opacity-50"
              >
                <div className="text-[13px] font-medium text-[#404040]">{o.label}</div>
                {o.resultingStatePreview && (
                  <div className="mt-0.5 text-[11px] text-[#9aa0a6]">→ {o.resultingStatePreview}</div>
                )}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-[#9aa0a6]">원하시면 직접 말씀해 주세요.</p>
        </div>
      </div>
    </div>
  );
}
