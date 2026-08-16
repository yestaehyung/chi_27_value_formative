"use client";

// 네이버 쇼핑형 세로 리스트 행 (2026-07-16, 수정안 3 전용 실험) — 캐러셀 카드 대신
// 상품 1건 = 1행: [상품명 헤더] → [큰 이미지 | 가격·평점·판매자 메타] → [상품별 설명 문단]
// → [피드백 버튼]. 데이터는 ProductCard와 동일한 Impression/Product 필드만 사용
// (도착 예정일 등 없는 정보는 표시하지 않음). 가격 계산식은 ProductCard와 동일.

import { Impression } from "@/lib/types";
import ProductFeedbackButtons, { FeedbackPayload } from "./ProductFeedbackButtons";
import { formatStudyPrice, productDescription, productTitle, productUsd, tr } from "@/lib/studyI18n";

const LETTERS = ["A", "B", "C", "D", "E"];

export default function ProductListRow({
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
  const displayTitle = productTitle(p);
  const displayDescription = productDescription(p);
  // build-time price is the median 정가(list); 실거래가 = 정가 × (1 − 평균 할인율)
  const discountPct = p.discountRate && p.discountRate > 0 ? Math.round(p.discountRate * 100) : 0;
  const realPrice = discountPct > 0 ? Math.round((p.price * (1 - p.discountRate!)) / 10) * 10 : p.price;

  return (
    <div className="msg-in py-5 first:pt-1" style={{ animationDelay: `${index * 80}ms` }}>
      {/* 상품명 헤더 */}
      <div className="mb-3 text-[15px] font-bold leading-snug text-[#191919]">{displayTitle}</div>

      <div className="flex gap-5">
        {/* 큰 이미지 (없으면 레터마크 폴백) */}
        <div className="flex h-36 w-36 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[#f5f6f8] sm:h-44 sm:w-44">
          {p.imageUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={p.imageUrl}
              alt={displayTitle}
              loading="lazy"
              className="h-full w-full object-contain"
              style={{ outline: "1px solid rgba(0,0,0,0.1)", outlineOffset: "-1px" }}
            />
          ) : (
            <span className="brand-mark h-9 w-9 rounded-lg text-sm">{LETTERS[index] ?? index + 1}</span>
          )}
        </div>

        {/* 가격·평점·판매자 메타 */}
        <div className="min-w-0 flex-1 space-y-1.5">
          {discountPct > 0 && (
            <div className="text-[13px] text-[#b0b8c1] line-through tabular-nums">
              {formatStudyPrice(p.price, productUsd(p))}
            </div>
          )}
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            {discountPct > 0 && <span className="text-lg font-extrabold text-[#e5392f]">{discountPct}%</span>}
            <span className="text-xl font-extrabold tracking-tight text-[#191919] tabular-nums">
              {formatStudyPrice(realPrice, discountPct > 0 ? null : productUsd(p))}
            </span>
            <span className="text-xs text-[#606060]">
              {p.deliveryFee ? `${tr("배송비", "Shipping")} ${formatStudyPrice(p.deliveryFee)}` : tr("무료배송", "Free shipping")}
            </span>
          </div>
          {(p.rating != null || p.reviewCount != null) && (
            <div className="text-[13px] tabular-nums text-[#404040]">
              <span className="text-[#f59e0b]">★</span> {p.rating}
              {p.reviewCount != null && <span className="text-[#9aa0a6]"> · {tr("리뷰", "Reviews")} {p.reviewCount.toLocaleString()}</span>}
            </div>
          )}
          {p.sellerName && (
            <div className="flex flex-wrap items-center gap-1.5 text-[13px] text-[#606060]">
              {p.sellerName}
              {p.sellerGrade && (
                <span className="rounded border border-[#e4e8eb] bg-[#f5f6f8] px-1.5 py-0.5 text-[10px] font-semibold text-[#5f6368]">
                  {p.sellerGrade}
                </span>
              )}
            </div>
          )}

          {/* 맞는 점(✓) / 애매한 점(~) — 부분 정직 고지 유지 (기존 카드와 동일 데이터) */}
          {(impression.matchedIntentions.length > 0 || impression.weakIntentions.length > 0) && (
            <div className="space-y-1 pt-1 text-[12px] leading-snug text-[#404040]">
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

        {/* 좋아요/싫어요/자세히/구매 — 상품 옆 세그먼트 스택 (얇게) */}
        <div className="w-16 shrink-0 self-start">
          <ProductFeedbackButtons
            vertical
            given={givenFeedback}
            disabled={disabled}
            onFeedback={(payload) => onFeedback(p.id, payload)}
            productTitle={displayTitle}
          />
        </div>
      </div>

      {/* 상품별 설명 — 사양 문단(상품 데이터의 description) + 개인화 근거(rerank의
          recommendationReason)를 본문 크기로. 스크린샷처럼 사실 → 맥락 순서. */}
      {(displayDescription || impression.recommendationReason) && (
        <div className="mt-4 space-y-2 text-pretty text-[15px] leading-relaxed text-[#191919]">
          {displayDescription && <p>{displayDescription}</p>}
          {impression.recommendationReason && (
            <p>
              {impression.recommendationReason}
              {p.sellerName && (
                <span className="ml-2 inline-block align-middle rounded-full border border-[#e4e8eb] bg-[#f5f6f8] px-2.5 py-1 text-[11px] font-medium text-[#5f6368]">
                  {p.sellerName}
                </span>
              )}
            </p>
          )}
        </div>
      )}

    </div>
  );
}
