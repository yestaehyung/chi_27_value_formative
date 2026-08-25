"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { tr } from "@/lib/studyI18n";

const REASON_CODES = [
  { code: "too_cheap_looking", label: tr("너무 저렴해 보여요", "Looks too cheap") },
  { code: "too_expensive", label: tr("너무 비싸요", "Too expensive") },
  { code: "not_trustworthy", label: tr("믿음이 안 가요", "Does not seem trustworthy") },
  { code: "low_long_term_reviews", label: tr("오래 쓴 리뷰가 적어요", "Not enough long-term reviews") },
  { code: "too_common", label: tr("너무 흔해요", "Too common") },
  { code: "bad_design", label: tr("디자인이 별로예요", "I do not like the design") },
  { code: "other", label: tr("기타", "Other") },
];

export type FeedbackPayload = {
  type: string;
  reasonCode?: string;
  reasonText?: string;
};

export default function ProductFeedbackButtons({
  given,
  onFeedback,
  disabled,
  productTitle,
  vertical = false, // 세로 스택 (리스트형 행에서 상품 옆 배치용) — 기본은 기존 가로 4열
}: {
  given: string[]; // feedback types already given for this product
  onFeedback: (payload: FeedbackPayload) => void;
  disabled?: boolean;
  productTitle?: string;
  vertical?: boolean;
}) {
  const [showReason, setShowReason] = useState(false);
  const [reasonCode, setReasonCode] = useState<string>("too_cheap_looking");
  const [reasonText, setReasonText] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setShowReason(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const has = (t: string) => given.includes(t);

  const submitDislike = () => {
    onFeedback({ type: "dislike", reasonCode, reasonText: reasonText.trim() || undefined });
    setShowReason(false);
    setReasonText("");
  };

  // 싫어요 이유 — 좁은 카드폭에서 해방되도록 모달(portal)로. 가로/세로 두 레이아웃 공용.
  const reasonModal = (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={() => setShowReason(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={tr("싫어요 이유", "Dislike reason")}
        className="flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-[#f0f2f4] px-5 py-3.5">
          <div className="min-w-0">
            <div className="text-sm font-bold text-[#191919]">{tr("이 상품, 어떤 점이 별로였어요?", "What did you dislike about this product?")}</div>
            {productTitle && <div className="mt-0.5 truncate text-xs text-[#9aa0a6]">{productTitle}</div>}
          </div>
          <button
            onClick={() => setShowReason(false)}
            className="-mr-2 -mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-[#9aa0a6] transition-colors duration-150 hover:bg-[#f0f2f4] hover:text-[#191919] active:scale-[0.92]"
            aria-label={tr("닫기", "Close")}
          >✕</button>
        </div>

        <div className="overflow-y-auto p-5">
          <div className="flex flex-wrap gap-2">
            {REASON_CODES.map((r) => (
              <button
                key={r.code}
                onClick={() => setReasonCode(r.code)}
                className={`rounded-full border px-3 py-1.5 text-sm transition ${
                  reasonCode === r.code
                    ? "border-rose-400 bg-rose-50 font-medium text-rose-700"
                    : "border-[#e4e8eb] bg-white text-[#606060] hover:border-rose-300"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>

          <textarea
            value={reasonText}
            onChange={(e) => setReasonText(e.target.value)}
            rows={3}
            placeholder={tr('자유롭게 적어주세요 (선택). 예: "선물인데 너무 저렴해 보이면 좀 그래요."', 'Add a comment if you wish. For example: "It looks too cheap for a gift."')}
            className="mt-4 w-full resize-none rounded-xl border border-[#e4e8eb] px-3 py-2.5 text-sm leading-relaxed focus:border-rose-300 focus:outline-none"
          />
        </div>

        <div className="flex justify-end gap-2 border-t border-[#f0f2f4] px-5 py-3">
          <button className="btn px-4 py-2 text-sm" onClick={() => setShowReason(false)}>{tr("취소", "Cancel")}</button>
          <button className="btn btn-danger px-4 py-2 text-sm font-semibold" onClick={submitDislike}>
            {tr("싫어요 보내기", "Submit Dislike")}
          </button>
        </div>
      </div>
    </div>
  );

  // 세로 모드 — 상품 옆 좁은 컬럼용 세그먼트 스택: 구분선으로 나뉜 한 덩어리 (버튼 4개가
  // 따로 노는 것보다 시각 부피가 작다). 행 높이는 40px 유지(핵심 인터랙션 히트 영역).
  if (vertical) {
    const row = "min-h-11 w-full px-2 text-[11px] font-medium text-[#5f6368] transition-[background-color,color] duration-150 hover:bg-[#fafbfc] disabled:opacity-50";
    return (
      <div className="flex w-full flex-col divide-y divide-[#f0f2f4] overflow-hidden rounded-xl border border-[#e4e8eb] bg-white">
        <button
          className={`${row} ${has("like") ? "bg-emerald-50 font-semibold text-emerald-700" : ""}`}
          disabled={disabled || has("like")}
          onClick={() => onFeedback({ type: "like" })}
        >
          {tr("좋아요", "Like")}
        </button>
        <button
          className={`${row} ${has("dislike") ? "bg-rose-50 font-semibold text-rose-700" : ""}`}
          disabled={disabled || has("dislike")}
          onClick={() => setShowReason(true)}
        >
          {tr("싫어요", "Dislike")}
        </button>
        <button
          className={row}
          disabled={disabled || has("view_detail")}
          onClick={() => onFeedback({ type: "view_detail" })}
        >
          {tr("자세히", "Details")}
        </button>
        <button
          className={`${row} ${has("purchase") ? "bg-emerald-600 font-semibold text-white" : ""}`}
          disabled={disabled || has("purchase")}
          onClick={() => onFeedback({ type: "purchase" })}
        >
          {tr("구매", "Purchase")}
        </button>

        {mounted && showReason && createPortal(reasonModal, document.body)}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-4 gap-1.5">
      {/* min-h-10(40px): 연구의 핵심 인터랙션이라 최소 히트 영역 40px 보장 */}
      <button
        className={`btn min-h-11 px-2 text-xs ${has("like") ? "border-emerald-400 bg-emerald-50 text-emerald-700" : ""}`}
        disabled={disabled || has("like")}
        onClick={() => onFeedback({ type: "like" })}
      >
        👍 {tr("좋아요", "Like")}
      </button>
      <button
        className={`btn min-h-11 px-2 text-xs ${has("dislike") ? "border-rose-300 bg-rose-50 text-rose-700" : ""}`}
        disabled={disabled || has("dislike")}
        onClick={() => setShowReason(true)}
      >
        👎 {tr("싫어요", "Dislike")}
      </button>
      <button
        className="btn min-h-11 px-2 text-xs"
        disabled={disabled || has("view_detail")}
        onClick={() => onFeedback({ type: "view_detail" })}
      >
        {tr("자세히", "Details")}
      </button>
      <button
        className={`btn min-h-11 px-2 text-xs ${has("purchase") ? "border-emerald-500 bg-emerald-600 text-white" : ""}`}
        disabled={disabled || has("purchase")}
        onClick={() => onFeedback({ type: "purchase" })}
      >
        {tr("구매", "Purchase")}
      </button>

      {mounted && showReason && createPortal(reasonModal, document.body)}
    </div>
  );
}
