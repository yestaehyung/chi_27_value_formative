import { ProductCueSummary } from "@/lib/types";

const PRICE_LABEL: Record<string, string> = {
  very_low: "초저가", low: "저가", mid: "중간 가격", high: "고가", very_high: "프리미엄",
};
const POP_LABEL: Record<string, string> = {
  niche: "니치", moderate: "보통 인기", popular: "인기", very_popular: "베스트셀러",
};

// "신뢰 낮음/보통/높음" 배지는 2026-07-06 제거 — 파생 기준(평점·리뷰수 합성)이 참가자에게
// 불투명해 스터디 중 "기준이 뭐냐" 질문이 나왔고, 원 데이터(★평점·리뷰 수)가 카드에
// 이미 그대로 보인다 (§36: 설명 불가능한 내부 판정을 참가자에게 라벨로 노출하지 않는다).
// trustCue 자체는 백엔드 cue_summary에 유지 (시뮬레이션·연구 분석용).
export default function ProductCueBadges({ cues }: { cues: ProductCueSummary }) {
  const badges = [
    { label: PRICE_LABEL[cues.priceCue], tone: cues.priceCue === "very_low" ? "amber" : "slate" },
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
