import { ProductCueSummary } from "@/lib/types";

const PRICE_LABEL: Record<string, string> = {
  very_low: "초저가", low: "저가", mid: "중간 가격", high: "고가", very_high: "프리미엄",
};
const TRUST_LABEL: Record<string, string> = { low: "신뢰 낮음", medium: "신뢰 보통", high: "신뢰 높음" };
const POP_LABEL: Record<string, string> = {
  niche: "니치", moderate: "보통 인기", popular: "인기", very_popular: "베스트셀러",
};

export default function ProductCueBadges({ cues }: { cues: ProductCueSummary }) {
  const badges = [
    { label: PRICE_LABEL[cues.priceCue], tone: cues.priceCue === "very_low" ? "amber" : "slate" },
    { label: TRUST_LABEL[cues.trustCue], tone: cues.trustCue === "high" ? "emerald" : "slate" },
    ...(cues.popularityCue !== "niche" ? [{ label: POP_LABEL[cues.popularityCue], tone: "slate" }] : []),
    ...(cues.noveltyCue === "distinctive" ? [{ label: "차별적", tone: "indigo" }] : []),
  ];
  const toneCls: Record<string, string> = {
    slate: "bg-[#f5f6f8] text-[#606060]",
    emerald: "bg-[#ecfdf5] text-[#047857]",
    amber: "bg-[#fffbe6] text-[#8a6d00]",
    indigo: "bg-[#eaf4ff] text-[#0073e6]",
  };
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b, i) => (
        <span key={i} className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${toneCls[b.tone]}`}>
          {b.label}
        </span>
      ))}
    </div>
  );
}
