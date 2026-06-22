"use client";

import { useState } from "react";
import { ValueAnchor } from "@/lib/types";

// 5-anchor = Theory of Consumption Values (TCV) trait 층.
// intention→value 매핑(anchor_mapper.TRAIT_ANCHORS)이 채우는 축과 1:1.
// (옛 Hedonic/Utilitarian 축은 2-tier 리팩토링 전 잔재라 제거 — 항상 0이었음.
//  진짜 쇼핑동기 7차원 MOTIVATION_DIMS 는 대화로 끌어내 motivationScores 에 별도 저장.)
// 축 라벨은 이론 용어(영문) 그대로 사용
const ANCHORS: { key: ValueAnchor; label: string; theory: string; meaning: string }[] = [
  { key: "Functional", label: "Functional", theory: "TCV Functional value", meaning: "성능·신뢰성·내구성·가격 대비 효용" },
  { key: "Social", label: "Social", theory: "TCV Social value", meaning: "사회집단 연상·사회적 이미지·체면·관계" },
  { key: "Emotional", label: "Emotional", theory: "TCV Emotional value", meaning: "제품이 주는 감정 — 안심·신뢰(긍정), 불안·후회 회피(부정)" },
  { key: "Epistemic", label: "Epistemic", theory: "TCV Epistemic value", meaning: "호기심·새로움·정보 탐색·지식 욕구" },
  { key: "Conditional", label: "Conditional", theory: "TCV Conditional value", meaning: "특정 상황·시점·용도에서만 발생하는 효용" },
];

type Contributor = {
  topicLabel: string;
  intensity: number;
  confidence: string;
  evidenceStrength: string;
  decisionImpact: string;
  temporalStatus: string;
  inConflict?: boolean;
  contribution: number;
};

export type AnchorBreakdown = Record<string, { confirmedScore: number; contributors: Contributor[] }>;

const LEVEL_KO: Record<string, string> = { low: "약함", medium: "보통", high: "강함" };
const CONF_KO: Record<string, string> = { confirmed: "직접 말함", inferred: "맥락으로 추측", weak: "약한 추정" };
const TEMPORAL_KO: Record<string, string> = { emerging: "새로 등장", active: "활성", weakened: "약화됨", resolved: "해소됨" };

export default function AnchorRadar({
  scores,
  breakdown,
  size = 180,
  onSelect,
}: {
  scores: Partial<Record<ValueAnchor, number>>;
  breakdown?: AnchorBreakdown;
  size?: number;
  onSelect?: (anchor: ValueAnchor | null) => void;
}) {
  const [selected, setSelected] = useState<ValueAnchor | null>(null);
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 26;
  const n = ANCHORS.length;

  const point = (i: number, value: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + Math.cos(angle) * r * value, cy + Math.sin(angle) * r * value];
  };
  const polygon = (value: (i: number) => number) =>
    ANCHORS.map((_, i) => point(i, value(i)).join(",")).join(" ");

  const hasBreakdown = breakdown && Object.keys(breakdown).length > 0;
  const sel = selected ? ANCHORS.find((a) => a.key === selected)! : null;
  const selData = selected && breakdown ? breakdown[selected] : null;

  return (
    <div>
      <svg width={size} height={size} className="mx-auto block overflow-visible">
        {[0.33, 0.66, 1].map((g) => (
          <polygon key={g} points={polygon(() => g)} fill="none" stroke="#e4e8eb" strokeWidth={1} />
        ))}
        {ANCHORS.map((_, i) => {
          const [x, y] = point(i, 1);
          return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e4e8eb" strokeWidth={1} />;
        })}

        {/* 전체(확인+추론) — 연한 영역 */}
        <polygon
          points={polygon((i) => Math.min(scores[ANCHORS[i].key] ?? 0, 1))}
          fill="rgba(79,70,229,0.08)"
          stroke="#a5b4fc"
          strokeWidth={1.2}
          strokeDasharray="4 2"
        />
        {/* 확인된 근거(confirmed)만 — 진한 영역 (§7.3 intensity vs confidence) */}
        {hasBreakdown && (
          <polygon
            points={polygon((i) => Math.min(breakdown![ANCHORS[i].key]?.confirmedScore ?? 0, 1))}
            fill="rgba(79,70,229,0.20)"
            stroke="#4f46e5"
            strokeWidth={1.8}
          />
        )}

        {ANCHORS.map((a, i) => {
          const [x, y] = point(i, 1.24);
          const v = scores[a.key] ?? 0;
          const isSel = selected === a.key;
          return (
            <g key={a.key} className="cursor-pointer" onClick={() => { const next = isSel ? null : a.key; setSelected(next); onSelect?.(next); }}>
              <circle cx={x} cy={y - 3} r={13} fill={isSel ? "#eef2ff" : "transparent"} />
              <text x={x} y={y - 3} textAnchor="middle" dominantBaseline="middle"
                    fontSize={10} fontWeight={isSel ? 700 : 400}
                    className={isSel ? "fill-[#4f46e5]" : "fill-[#787c82]"}>
                {a.label}
              </text>
              <text x={x} y={y + 8} textAnchor="middle" fontSize={8} className="fill-[#b0b8c1]">
                {v > 0 ? v.toFixed(2) : "–"}
              </text>
            </g>
          );
        })}
      </svg>

      {hasBreakdown && (
        <div className="mt-1 flex items-center justify-center gap-3 text-[10px] text-[#9aa0a6]">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-3 rounded-sm bg-[#4f46e5]/30 ring-1 ring-[#4f46e5]" /> 직접 말한 것
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-3 rounded-sm bg-[#4f46e5]/10 ring-1 ring-[#a5b4fc]" /> 맥락 추측 포함
          </span>
        </div>
      )}

      {/* 축 클릭 → 이론 근거 분해 (§7.2~7.3) */}
      {sel && (
        <div className="msg-in mt-2 rounded-xl bg-[#f5f6f8] p-3 text-[11px]">
          <span className="font-bold text-[#191919]">{sel.label}</span>
          <div className="mt-0.5 text-[#606060]">{sel.meaning}</div>
          {selData && selData.contributors.length > 0 ? (
            <div className="mt-2 space-y-1.5 border-t border-[#e4e8eb] pt-2">
              {selData.contributors.map((c, i) => (
                <div key={i}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-[#404040]">{c.topicLabel}</span>
                    <span className="font-mono tabular-nums text-[#4f46e5]">+{c.contribution.toFixed(2)}</span>
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-1 text-[9px]">
                    <span className={`rounded px-1 py-0.5 ${c.confidence === "confirmed" ? "bg-[#ecfdf5] text-[#047857]" : "bg-white text-[#787c82]"}`}>
                      {CONF_KO[c.confidence] ?? c.confidence}
                    </span>
                    <span className="rounded bg-white px-1 py-0.5 text-[#787c82]">근거 {LEVEL_KO[c.evidenceStrength] ?? c.evidenceStrength}</span>
                    <span className="rounded bg-white px-1 py-0.5 text-[#787c82]">결정영향 {LEVEL_KO[c.decisionImpact] ?? c.decisionImpact}</span>
                    <span className="rounded bg-white px-1 py-0.5 text-[#787c82]">{TEMPORAL_KO[c.temporalStatus] ?? c.temporalStatus}</span>
                    {c.inConflict && <span className="rounded bg-[#fffbe6] px-1 py-0.5 text-[#8a6d00]">충돌 중 ↓</span>}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-2 border-t border-[#e4e8eb] pt-2 text-[#b0b8c1]">아직 이 가치에 연결된 근거가 없어요.</div>
          )}
        </div>
      )}
      {hasBreakdown && !sel && (
        <div className="mt-1 text-center text-[10px] text-[#b0b8c1]">축 이름을 누르면, 제가 왜 그렇게 봤는지 근거를 볼 수 있어요</div>
      )}
    </div>
  );
}
