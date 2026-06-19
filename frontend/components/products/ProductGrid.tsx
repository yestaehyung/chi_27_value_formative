"use client";

import { Impression } from "@/lib/types";
import ProductCard from "./ProductCard";
import { FeedbackPayload } from "./ProductFeedbackButtons";

export default function ProductGrid({
  impressions,
  feedbackByProduct,
  onFeedback,
  disabled,
}: {
  impressions: Impression[];
  feedbackByProduct: Record<string, string[]>;
  onFeedback: (productId: string, payload: FeedbackPayload) => void;
  disabled?: boolean;
}) {
  if (impressions.length === 0) {
    return (
      <div className="card flex h-32 items-center justify-center text-sm text-slate-400">
        대화를 시작하면 추천 상품이 여기에 표시됩니다
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {impressions.map((imp, i) => (
        <ProductCard
          key={imp.id}
          impression={imp}
          index={i}
          givenFeedback={feedbackByProduct[imp.productId] ?? []}
          onFeedback={onFeedback}
          disabled={disabled}
        />
      ))}
    </div>
  );
}
