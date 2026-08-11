"use client";

// ③ 최종 선택 확정 모달 (2026-08-11) — "이 쇼핑 마치기" 직후, 사후 설문·기준 검증 전에
// 이번 세션에서 본 상품 중 최종 하나를 잠근다. 기준을 뜯어보는 단계(④)가 선택에
// 영향을 주지 못하게 하는 절차적 잠금이며, 화면에 기준 정보가 없어 세 조건이 동일하다.
//
// "이 중에는 없어요" 탈출구를 둔다 — 억지 선택은 쓰레기 데이터가 되고, 왜 없는지
// 이유 텍스트는 그 자체로 추천 실패 신호다.
import { useState } from "react";
import { formatStudyPrice, tr } from "@/lib/studyI18n";

export type SeenProduct = {
  productId: string;
  title: string;
  price: number | null;
  imageUrl: string | null;
  liked: boolean;
  purchased: boolean;
};

/** 처음부터 펼쳐 보여줄 상품 수 — 긴 세션(노출 수십 개)에서 목록이 압도하지 않게.
 *  입력은 구매→좋아요→최근 순으로 정렬돼 오므로, 접히는 건 오래전에 본 무반응 상품뿐이다. */
const VISIBLE_CAP = 20;

export default function FinalChoiceModal({
  products,
  submitting = false,
  onConfirm,
}: {
  products: SeenProduct[];
  submitting?: boolean;
  /** productId 확정, 또는 (null, 이유)로 "이 중에는 없어요" */
  onConfirm: (productId: string | null, noneReason?: string) => void;
}) {
  // 대화 중 '구매'를 누른 상품이 있으면 그걸 기본 선택으로 — 가장 강한 선택 신호.
  const [picked, setPicked] = useState<string | null>(
    () => products.find((p) => p.purchased)?.productId ?? null,
  );
  const [noneMode, setNoneMode] = useState(false);
  const [noneReason, setNoneReason] = useState("");
  const [showAll, setShowAll] = useState(false);

  const visible = showAll ? products : products.slice(0, VISIBLE_CAP);
  const hidden = products.length - VISIBLE_CAP;
  const canSubmit = noneMode ? noneReason.trim().length > 0 : picked !== null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card flex max-h-[85dvh] w-full max-w-2xl flex-col p-5">
        <h2 className="text-base font-bold text-[#191919]">{tr("마치기 전에, 최종 선택을 확정해 주세요", "Confirm Your Final Choice Before Finishing")}</h2>
        <p className="mt-1 text-xs leading-relaxed text-[#5f6368]">
          {tr("지금까지 본 상품 중 실제로 산다면 고를 하나를 선택해 주세요. 확정 후에는 바꿀 수 없어요.", "Choose the one product you would purchase from those you have seen. You cannot change your choice after confirming it.")}
        </p>

        <div className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          {visible.map((p) => {
            const on = !noneMode && picked === p.productId;
            return (
              <button
                key={p.productId}
                onClick={() => { setPicked(p.productId); setNoneMode(false); }}
                aria-pressed={on}
                className={`flex w-full items-center gap-3 rounded-xl border p-2.5 text-left transition-[border-color,background-color] duration-150 ${
                  on ? "border-[#4f46e5] bg-[#f5f5ff]" : "border-[#e4e8eb] bg-white hover:border-[#4f46e5]"
                }`}
              >
                {p.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={p.imageUrl}
                    alt=""
                    className="h-12 w-12 shrink-0 rounded-lg object-cover"
                    style={{ outline: "1px solid rgba(0,0,0,0.1)", outlineOffset: "-1px" }}
                  />
                ) : (
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[#f5f6f8] text-lg">🛒</span>
                )}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-[#191919]">{p.title}</div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-[#9aa0a6]">
                    {p.price != null && <span className="tabular-nums">{formatStudyPrice(p.price)}</span>}
                    {p.purchased && <span className="font-semibold text-[#047857]">{tr("구매 누른 상품", "Marked for purchase")}</span>}
                    {p.liked && !p.purchased && <span className="text-[#4f46e5]">♥ {tr("좋아요한 상품", "Liked product")}</span>}
                  </div>
                </div>
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold transition-[background-color,border-color,color] duration-150 ${
                    on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#d5d9dd] text-transparent"
                  }`}
                  aria-hidden
                >
                  ✓
                </span>
              </button>
            );
          })}
          {!showAll && hidden > 0 && (
            <button
              onClick={() => setShowAll(true)}
              className="w-full rounded-xl border border-dashed border-[#d5d9dd] py-2 text-xs text-[#9aa0a6] transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5]"
            >
              {tr(`이전에 본 상품 ${hidden}개 더 보기`, `Show ${hidden} more previously viewed ${hidden === 1 ? "product" : "products"}`)}
            </button>
          )}
        </div>

        <div className="mt-3 border-t border-[#f0f2f4] pt-3">
          <button
            onClick={() => { setNoneMode((v) => !v); setPicked(null); }}
            aria-pressed={noneMode}
            className={`text-xs transition-colors duration-150 ${
              noneMode ? "font-semibold text-[#4f46e5]" : "text-[#9aa0a6] hover:text-[#4f46e5]"
            }`}
          >
            {tr("이 중에는 없어요", "None of These Products")}
          </button>
          {noneMode && (
            <textarea
              value={noneReason}
              onChange={(e) => setNoneReason(e.target.value)}
              autoFocus
              rows={2}
              placeholder={tr("어떤 점이 맞지 않았는지 알려주세요 (예: 원하는 색상이 없었어요)", "Please tell us what did not fit your needs (for example, the color you wanted was unavailable).")}
              className="mt-2 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs leading-relaxed focus:border-[#4f46e5] focus:outline-none"
            />
          )}
        </div>

        <button
          onClick={() => onConfirm(noneMode ? null : picked, noneMode ? noneReason.trim() : undefined)}
          disabled={!canSubmit || submitting}
          className="btn btn-primary mt-3 w-full py-2.5 text-sm"
        >
          {submitting ? tr("저장하는 중…", "Saving…") : noneMode ? tr("선택 없이 마치기", "Finish Without Selecting") : tr("이 상품으로 확정", "Confirm This Product")}
        </button>
      </div>
    </div>
  );
}
