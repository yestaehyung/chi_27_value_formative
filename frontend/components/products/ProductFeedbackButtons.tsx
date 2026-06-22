"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

const REASON_CODES = [
  { code: "too_cheap_looking", label: "너무 저렴해 보여요" },
  { code: "too_expensive", label: "너무 비싸요" },
  { code: "not_trustworthy", label: "믿음이 안 가요" },
  { code: "low_long_term_reviews", label: "오래 쓴 리뷰가 적어요" },
  { code: "too_common", label: "너무 흔해요" },
  { code: "bad_design", label: "디자인이 별로예요" },
  { code: "other", label: "기타" },
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
}: {
  given: string[]; // feedback types already given for this product
  onFeedback: (payload: FeedbackPayload) => void;
  disabled?: boolean;
  productTitle?: string;
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

  return (
    <div className="grid grid-cols-4 gap-1.5">
      <button
        className={`btn px-2 py-1 text-xs ${has("like") ? "border-emerald-400 bg-emerald-50 text-emerald-700" : ""}`}
        disabled={disabled || has("like")}
        onClick={() => onFeedback({ type: "like" })}
      >
        👍 좋아요
      </button>
      <button
        className={`btn px-2 py-1 text-xs ${has("dislike") ? "border-rose-300 bg-rose-50 text-rose-700" : ""}`}
        disabled={disabled || has("dislike")}
        onClick={() => setShowReason(true)}
      >
        👎 싫어요
      </button>
      <button
        className="btn px-2 py-1 text-xs"
        disabled={disabled || has("view_detail")}
        onClick={() => onFeedback({ type: "view_detail" })}
      >
        자세히
      </button>
      <button
        className={`btn px-2 py-1 text-xs ${has("purchase") ? "border-emerald-500 bg-emerald-600 text-white" : ""}`}
        disabled={disabled || has("purchase")}
        onClick={() => onFeedback({ type: "purchase" })}
      >
        구매
      </button>

      {/* 싫어요 이유 — 좁은 카드폭에서 해방되도록 모달(portal)로 */}
      {mounted && showReason && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setShowReason(false)}
        >
          <div
            className="flex max-h-[85vh] w-full max-w-md flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-[#f0f2f4] px-5 py-3.5">
              <div className="min-w-0">
                <div className="text-sm font-bold text-[#191919]">이 상품, 어떤 점이 별로였어요?</div>
                {productTitle && <div className="mt-0.5 truncate text-xs text-[#9aa0a6]">{productTitle}</div>}
              </div>
              <button
                onClick={() => setShowReason(false)}
                className="-mr-2 -mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg leading-none text-[#9aa0a6] transition-colors duration-150 hover:bg-[#f0f2f4] hover:text-[#191919] active:scale-[0.92]"
                aria-label="닫기"
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
                placeholder={'자유롭게 적어주세요 (선택). 예: "선물인데 너무 저렴해 보이면 좀 그래요."'}
                className="mt-4 w-full resize-none rounded-xl border border-[#e4e8eb] px-3 py-2.5 text-sm leading-relaxed focus:border-rose-300 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-2 border-t border-[#f0f2f4] px-5 py-3">
              <button className="btn px-4 py-2 text-sm" onClick={() => setShowReason(false)}>취소</button>
              <button className="btn btn-danger px-4 py-2 text-sm font-semibold" onClick={submitDislike}>
                싫어요 보내기
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
