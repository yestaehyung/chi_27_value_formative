"use client";

import { useState } from "react";

// 쇼핑 동기 7축 = Arnold & Reynolds(2003) 헤도닉 6 + Babin Utilitarian.
// 설문 대신 대화에서 키워드로 감지·누적되는 *상황적* 동기 (anchor_mapper.MOTIVATION_DIMS).
// AnchorRadar(가치 5축)와 동일한 비주얼, 데이터만 동기로 — 단일 폴리곤.
const DIMS: { key: string; label: string; meaning: string }[] = [
  { key: "Adventure", label: "Adventure", meaning: "새로운 걸 발견·구경하는 재미로 둘러봄" },
  { key: "Gratification", label: "Gratification", meaning: "기분전환·스트레스 해소·나에게 주는 보상" },
  { key: "Role", label: "Role", meaning: "남을 위해 골라주는 즐거움 (선물)" },
  { key: "BargainValue", label: "Bargain", meaning: "할인·가성비·'잘 샀다'는 득템의 즐거움" },
  { key: "SocialShopping", label: "Social", meaning: "함께 고르거나 의견을 나누며 하는 쇼핑" },
  { key: "Idea", label: "Idea", meaning: "트렌드·신제품 정보를 살피려는 쇼핑" },
  { key: "Utilitarian", label: "Utilitarian", meaning: "필요한 걸 효율적으로 빠르게 끝내기" },
];

const COVER = 0.4; // 이 이상 = 대화에서 드러남 / 미만 = 아직 안 떠봄(흐리게)

export default function MotivationRadar({
  scores,
  size = 260,
  onSelect,
}: {
  scores: Record<string, number>;
  size?: number;
  onSelect?: (dim: string | null) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 30;
  const n = DIMS.length;

  const point = (i: number, value: number) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + Math.cos(angle) * r * value, cy + Math.sin(angle) * r * value];
  };
  const polygon = (value: (i: number) => number) =>
    DIMS.map((_, i) => point(i, value(i)).join(",")).join(" ");

  const sel = selected ? DIMS.find((d) => d.key === selected)! : null;

  return (
    <div>
      <svg width={size} height={size} className="mx-auto block overflow-visible">
        {[0.33, 0.66, 1].map((g) => (
          <polygon key={g} points={polygon(() => g)} fill="none" stroke="#e4e8eb" strokeWidth={1} />
        ))}
        {DIMS.map((_, i) => {
          const [x, y] = point(i, 1);
          return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e4e8eb" strokeWidth={1} />;
        })}

        {/* 동기 폴리곤 (단일) */}
        <polygon
          points={polygon((i) => Math.min(scores[DIMS[i].key] ?? 0, 1))}
          fill="rgba(79,70,229,0.14)"
          stroke="#4f46e5"
          strokeWidth={1.8}
        />

        {DIMS.map((d, i) => {
          const [x, y] = point(i, 1.26);
          const v = scores[d.key] ?? 0;
          const isSel = selected === d.key;
          const covered = v >= COVER;
          return (
            <g key={d.key} className="cursor-pointer" onClick={() => { const next = isSel ? null : d.key; setSelected(next); onSelect?.(next); }}>
              <circle cx={x} cy={y - 3} r={13} fill={isSel ? "#eef2ff" : "transparent"} />
              <text
                x={x} y={y - 3} textAnchor="middle" dominantBaseline="middle"
                fontSize={9.5} fontWeight={isSel ? 700 : 400}
                className={isSel ? "fill-[#4f46e5]" : covered ? "fill-[#787c82]" : "fill-[#c8ccd0]"}
              >
                {d.label}
              </text>
              <text x={x} y={y + 8} textAnchor="middle" fontSize={8} className="fill-[#b0b8c1]">
                {v > 0 ? v.toFixed(2) : "–"}
              </text>
            </g>
          );
        })}
      </svg>

      {sel ? (
        <div className="msg-in mt-2 rounded-xl bg-[#f5f6f8] p-3 text-[11px]">
          <div className="font-bold text-[#191919]">{sel.label}</div>
          <div className="mt-0.5 text-[#606060]">{sel.meaning}</div>
          <div className="mt-1.5 border-t border-[#e4e8eb] pt-1.5 text-[#9aa0a6]">
            {(scores[sel.key] ?? 0) >= COVER
              ? "대화에서 이 동기가 보였어요."
              : "아직 대화에서 드러나지 않은 동기예요 — 에이전트가 떠볼 후보예요."}
          </div>
        </div>
      ) : (
        <div className="mt-1 text-center text-[10px] text-[#b0b8c1]">
          축 이름을 누르면 설명이 나와요. 흐리게 표시된 건 아직 대화에서 드러나지 않은 동기예요
        </div>
      )}
    </div>
  );
}
