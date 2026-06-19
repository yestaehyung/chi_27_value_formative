"use client";

import { useState } from "react";
import { Conflict } from "@/lib/types";

export default function ConflictCard({
  conflict,
  onResolve,
  onDismiss,
}: {
  conflict: Conflict;
  onResolve: (optionId: string, manualText?: string) => void;
  onDismiss?: () => void;
}) {
  const [manualMode, setManualMode] = useState(false);
  const [manualText, setManualText] = useState("");
  const [hovered, setHovered] = useState<string | null>(null);

  const options = conflict.suggestedResolutions ?? [];
  const hoveredOption = options.find((o) => o.id === hovered);

  return (
    <div className="msg-in card overflow-hidden border-[#ecc94b]">
      <div className="flex items-start justify-between bg-[#fffbe6] px-4 py-3">
        <h3 className="flex items-center gap-2 text-sm font-bold text-[#191919]">
          <span className="flex h-5 w-5 items-center justify-center rounded bg-[#f0b429] text-xs font-extrabold text-white">!</span>
          기준이 바뀐 것 같아요
        </h3>
        {onDismiss && (
          <button onClick={onDismiss} className="text-xs text-[#8a6d00] hover:underline">나중에</button>
        )}
      </div>

      <div className="p-4">
        <p className="text-xs leading-relaxed text-[#404040]">{conflict.explanationForUser}</p>

        <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-xl bg-[#f5f6f8] p-2.5">
            <div className="font-semibold text-[#9aa0a6]">지금까지 이해</div>
            <div className="mt-0.5 text-[#404040]">{conflict.oldAssumption}</div>
          </div>
          <div className="rounded-xl bg-[#ecfdf5] p-2.5">
            <div className="font-semibold text-[#4f46e5]">방금 보인 것</div>
            <div className="mt-0.5 text-[#404040]">{conflict.newSignal}</div>
          </div>
        </div>

        {!manualMode ? (
          <div className="mt-3 space-y-1.5">
            {options.filter((o) => o.action !== "manual_edit").map((o) => (
              <button
                key={o.id}
                onClick={() => onResolve(o.id)}
                onMouseEnter={() => setHovered(o.id)}
                onMouseLeave={() => setHovered(null)}
                className="block w-full rounded-xl border border-[#e4e8eb] bg-white px-4 py-2.5 text-left text-xs font-medium text-[#404040] transition-colors duration-150 hover:border-[#4f46e5] hover:bg-[#f7fdf9] hover:text-[#047857]"
              >
                {o.label}
              </button>
            ))}
            {options.some((o) => o.action === "manual_edit") && (
              <button
                onClick={() => setManualMode(true)}
                className="block w-full rounded-xl border border-dashed border-[#c9cdd2] bg-white px-4 py-2.5 text-left text-xs text-[#787c82] transition hover:border-[#4f46e5] hover:text-[#047857]"
              >
                직접 수정하기
              </button>
            )}
            {hoveredOption && (
              <div className="rounded-xl bg-[#f5f6f8] px-3 py-2 text-[11px] text-[#606060]">
                → {hoveredOption.resultingStatePreview}
              </div>
            )}
          </div>
        ) : (
          <div className="mt-3">
            <textarea
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              rows={2}
              placeholder="원하는 기준을 직접 적어주세요"
              className="chat-input w-full resize-none px-3.5 py-2.5 text-xs focus:outline-none"
            />
            <div className="mt-2 flex justify-end gap-1.5">
              <button className="btn px-3 py-1.5 text-xs" onClick={() => setManualMode(false)}>취소</button>
              <button
                className="btn btn-primary px-3 py-1.5 text-xs"
                disabled={!manualText.trim()}
                onClick={() => onResolve("manual_edit", manualText.trim())}
              >
                이 기준으로 수정
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
