"use client";

import { Impression } from "@/lib/types";
import ProductCueBadges from "./ProductCueBadges";
import ProductFeedbackButtons, { FeedbackPayload } from "./ProductFeedbackButtons";

const LETTERS = ["A", "B", "C", "D", "E"];

export default function ProductCard({
  impression,
  index,
  givenFeedback,
  onFeedback,
  disabled,
}: {
  impression: Impression;
  index: number;
  givenFeedback: string[];
  onFeedback: (productId: string, payload: FeedbackPayload) => void;
  disabled?: boolean;
}) {
  const p = impression.product;
  if (!p) return null;
  const ltr = Math.round((p.longTermReviewRatio ?? 0) * 100);
  const showLtr = (p.longTermReviewRatio ?? 0) > 0;                                // Amazon엔 한달리뷰 없음(0) → 숨김
  const showSales = !!p.recentSalesCount && p.recentSalesCount !== p.reviewCount;  // Amazon은 판매량 없어 리뷰수 프록시 → 숨김
  // build-time price is the median 정가(list); 실거래가 = 정가 × (1 − 평균 할인율)
  const discountPct = p.discountRate && p.discountRate > 0 ? Math.round(p.discountRate * 100) : 0;
  const realPrice = discountPct > 0 ? Math.round((p.price * (1 - p.discountRate!)) / 10) * 10 : p.price;

  return (
    <div className="msg-in flex h-full flex-col gap-2">
      {/* 상품 정보 박스 (테두리) — flex-1 로 3개 카드 높이 맞춤 */}
      <div className="card flex flex-1 flex-col overflow-hidden transition-colors duration-150 hover:border-[#4f46e5]">
        {/* 상품 이미지 (네이버 검색 API enrichment) — 없으면 헤더의 레터마크로 폴백 */}
        {p.imageUrl && (
          <div className="h-36 w-full overflow-hidden bg-[#f5f6f8]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={p.imageUrl}
              alt={p.title}
              loading="lazy"
              className="h-full w-full object-contain"
              style={{ outline: "1px solid rgba(0,0,0,0.1)", outlineOffset: "-1px" }}
            />
          </div>
        )}
        {/* 헤더: 라벨 + 제목 · 가격 */}
        <div className="flex items-start justify-between gap-2.5 px-4 pt-4">
          <div className="flex min-w-0 items-start gap-2">
            <span className="brand-mark mt-px h-6 w-6 shrink-0 rounded-md text-[11px]">
              {LETTERS[index] ?? index + 1}
            </span>
            <span className="min-h-[2.4rem] text-sm font-bold leading-snug text-[#191919]">{p.title}</span>
          </div>
          <div className="shrink-0 whitespace-nowrap text-right tabular-nums">
            <div className="text-base font-extrabold tracking-tight text-[#191919]">
              {realPrice.toLocaleString()}원
            </div>
            {discountPct > 0 && (
              <div className="text-[10px] leading-tight">
                <span className="text-[#b0b8c1] line-through">{p.price.toLocaleString()}원</span>{" "}
                <span className="font-bold text-[#e5392f]">{discountPct}%↓</span>
              </div>
            )}
            <div className="text-[10px] text-[#9aa0a6]">
              배송비 {p.deliveryFee ? `${p.deliveryFee.toLocaleString()}원` : "무료"}
            </div>
          </div>
        </div>

        <div className="flex-1 space-y-3.5 px-4 pb-4 pt-3.5" data-tutorial={index === 0 ? "card-info" : undefined}>
          {/* 신뢰 지표 */}
          <div className="space-y-1.5 border-t border-[#f0f2f4] pt-3 text-[11px] tabular-nums text-[#606060]">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              <span className="flex items-center gap-1">
                <span className="text-[#f59e0b]">★</span>{p.rating}
                <span className="text-[#b0b8c1]">· 리뷰 {p.reviewCount?.toLocaleString()}</span>
              </span>
              {showLtr && <span>한달리뷰 <b className={ltr >= 30 ? "text-[#047857]" : "text-[#404040]"}>{ltr}%</b></span>}
              {showSales && <span>최근판매 {p.recentSalesCount?.toLocaleString()}건</span>}
            </div>
          </div>

          <ProductCueBadges cues={p.cueSummary} />

          {impression.recommendationReason && (
            <div className="rounded-xl bg-[#f5f6f8] px-3 py-2.5 text-[11px] leading-relaxed text-[#606060]">
              {impression.recommendationReason}
            </div>
          )}

          {/* 맞는 점(✓) / 애매한 점(~) — 깔끔한 체크행 */}
          {(impression.matchedIntentions.length > 0 || impression.weakIntentions.length > 0) && (
            <div className="space-y-1.5 text-[11px] leading-relaxed text-[#404040]">
              {impression.matchedIntentions.map((m, i) => (
                <div key={`m${i}`} className="flex gap-1.5">
                  <span className="mt-px shrink-0 font-bold text-[#047857]">✓</span>
                  <span>{m}</span>
                </div>
              ))}
              {impression.weakIntentions.map((m, i) => (
                <div key={`w${i}`} className="flex gap-1.5">
                  <span className="mt-px shrink-0 font-bold text-[#cc8b00]">~</span>
                  <span>{m}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 피드백 버튼 — 박스 바깥 좌측 하단 */}
      <div data-tutorial={index === 0 ? "card-feedback" : undefined}>
        <ProductFeedbackButtons
          given={givenFeedback}
          disabled={disabled}
          onFeedback={(payload) => onFeedback(p.id, payload)}
          productTitle={p.title}
        />
      </div>
    </div>
  );
}
