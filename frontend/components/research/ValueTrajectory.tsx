"use client";

import { Snapshot, ValueAnchor } from "@/lib/types";

// 7-anchor value trajectory (TCV 5 + Hedonic/Utilitarian)
const ANCHOR_COLORS: Record<ValueAnchor, string> = {
  Functional: "#0073e6",
  Social: "#e8590c",
  Emotional: "#e03131",
  Epistemic: "#9b59b6",
  Conditional: "#16a34a",
  Hedonic: "#f0b429",
  Utilitarian: "#0d9488",
};
const ANCHORS = Object.keys(ANCHOR_COLORS) as ValueAnchor[];

export default function ValueTrajectory({ snapshots }: { snapshots: Snapshot[] }) {
  if (snapshots.length < 2) {
    return <div className="text-sm text-[#9aa0a6]">궤적을 그리려면 snapshot이 2개 이상 필요해요.</div>;
  }

  const W = 760, H = 260, padL = 36, padR = 130, padT = 16, padB = 40;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const n = snapshots.length;
  const x = (i: number) => padL + (innerW * i) / (n - 1);
  const y = (v: number) => padT + innerH * (1 - Math.min(v, 1));

  // stage 구간 (연속된 같은 stage를 band로)
  const bands: { stage: string; from: number; to: number }[] = [];
  snapshots.forEach((s, i) => {
    const stage = s.stage ?? "?";
    const last = bands[bands.length - 1];
    if (last && last.stage === stage) last.to = i;
    else bands.push({ stage, from: i, to: i });
  });

  // stage별 dominant anchors (이론모듈 §8.3)
  const stageSummary = bands.map((b) => {
    const totals: Record<string, number> = {};
    for (let i = b.from; i <= b.to; i++) {
      for (const a of ANCHORS) totals[a] = (totals[a] ?? 0) + (snapshots[i].anchorScores?.[a] ?? 0);
    }
    const dominant = Object.entries(totals).sort((p, q) => q[1] - p[1]).slice(0, 2)
      .filter(([, v]) => v > 0).map(([k]) => k);
    return { ...b, dominant };
  });

  return (
    <div>
      <div className="overflow-x-auto">
        <svg width={W} height={H} className="min-w-[760px]">
          {/* stage bands */}
          {stageSummary.map((b, bi) => (
            <g key={bi}>
              <rect
                x={x(b.from)} y={padT}
                width={Math.max(x(b.to) - x(b.from), 2)} height={innerH}
                fill={bi % 2 === 0 ? "#f5f6f8" : "#fafbfc"}
              />
              <text x={(x(b.from) + x(b.to)) / 2} y={H - 22} fontSize={9} fill="#787c82" textAnchor="middle">
                {b.stage}
              </text>
              <text x={(x(b.from) + x(b.to)) / 2} y={H - 10} fontSize={8} fill="#b0b8c1" textAnchor="middle">
                {b.dominant.join("·")}
              </text>
            </g>
          ))}
          {/* grid */}
          {[0, 0.5, 1].map((g) => (
            <g key={g}>
              <line x1={padL} y1={y(g)} x2={padL + innerW} y2={y(g)} stroke="#e4e8eb" strokeWidth={1} />
              <text x={padL - 6} y={y(g) + 3} fontSize={9} fill="#b0b8c1" textAnchor="end">{g}</text>
            </g>
          ))}
          {/* anchor lines */}
          {ANCHORS.map((a) => {
            const pts = snapshots.map((s, i) => `${x(i)},${y(s.anchorScores?.[a] ?? 0)}`).join(" ");
            const lastV = snapshots[n - 1].anchorScores?.[a] ?? 0;
            return (
              <g key={a}>
                <polyline points={pts} fill="none" stroke={ANCHOR_COLORS[a]} strokeWidth={1.8} />
                {snapshots.map((s, i) => (
                  <circle key={i} cx={x(i)} cy={y(s.anchorScores?.[a] ?? 0)} r={2.2} fill={ANCHOR_COLORS[a]} />
                ))}
                <text x={padL + innerW + 8} y={y(lastV) + 3} fontSize={9.5} fill={ANCHOR_COLORS[a]}>
                  {a} {lastV.toFixed(2)}
                </text>
              </g>
            );
          })}
          {/* x ticks: turn index */}
          {snapshots.map((s, i) => (
            <text key={i} x={x(i)} y={padT + innerH + 11} fontSize={8} fill="#b0b8c1" textAnchor="middle">
              t{s.turnIndex}
            </text>
          ))}
        </svg>
      </div>
      <p className="mt-2 text-[11px] text-[#9aa0a6]">
        쇼핑 단계(stage)에 따라 가치 분포가 어떻게 이동하는지 보여줍니다 — 예: Hedonic 탐색 →
        Functional/Affective 수렴 (이론모듈 §8). 각 구간 아래는 해당 stage의 dominant anchor.
      </p>
    </div>
  );
}
