// 칩 타입 배지 (2026-07-21) — 색+텍스트로 자기설명. 색상만으로 타입을 전달하던
// D·E 위젯의 점(dot)을 대체한다. 스타일은 CurrentUnderstandingPanel의 배지와 동일
// (같은 디자인 언어 — 참가자가 패널·위젯 어디서 봐도 같은 표기).

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

export default function ChipTypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`inline-block shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold ${CHIP_STYLE[type] ?? CHIP_STYLE.nice_to_have}`}
    >
      {CHIP_TYPE_LABEL[type] ?? "선호"}
    </span>
  );
}
