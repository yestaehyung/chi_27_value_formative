"use client";

import { useState } from "react";
import { Snapshot } from "@/lib/types";
import AnchorRadar from "@/components/preference/AnchorRadar";

export default function SnapshotTimeline({ snapshots }: { snapshots: Snapshot[] }) {
  const [idx, setIdx] = useState(snapshots.length - 1);
  if (snapshots.length === 0) return <div className="text-sm text-slate-400">snapshot 없음</div>;
  const snap = snapshots[Math.min(idx, snapshots.length - 1)];

  return (
    <div>
      <div className="flex items-center gap-3">
        <input
          type="range" min={0} max={snapshots.length - 1} value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          className="flex-1 accent-emerald-600"
        />
        <span className="whitespace-nowrap font-mono text-xs text-slate-500">
          {idx + 1}/{snapshots.length} (turn {snap.turnIndex})
        </span>
      </div>

      <div className="mt-3 grid gap-4 md:grid-cols-[200px_1fr]">
        <AnchorRadar scores={snap.anchorScores} size={190} />
        <div className="space-y-2 text-xs">
          <div>
            <span className="font-semibold text-slate-500">우선순위:</span>{" "}
            {snap.priorityOrder.slice(0, 6).join(" → ") || "–"}
          </div>
          <div>
            <span className="font-semibold text-emerald-600">필수:</span>{" "}
            {snap.hardConstraints.join(" · ") || "–"}
          </div>
          <div>
            <span className="font-semibold text-sky-600">선호:</span>{" "}
            {snap.softPreferences.join(" · ") || "–"}
          </div>
          <div>
            <span className="font-semibold text-rose-600">제외:</span>{" "}
            {snap.avoidances.join(" · ") || "–"}
          </div>
          <div className="rounded-md bg-slate-50 p-2 text-slate-600">
            {snap.userVisibleSummary?.oneSentenceSummary}
          </div>
          {snap.uncertainty?.conflictIds?.length > 0 && (
            <div className="text-amber-600">⚠ open conflicts: {snap.uncertainty.conflictIds.length}</div>
          )}
        </div>
      </div>
    </div>
  );
}
