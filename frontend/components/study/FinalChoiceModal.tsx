"use client";

// ③ 결정 상태 확정 모달 (2026-08-11, 2026-08-13 4범주 개편 — 측정 계획 §5.1).
// "이 쇼핑 마치기" 직후, 확신 설문·기준 감사 전에 결정 상태를 잠근다. 기준을
// 뜯어보는 단계가 선택에 영향을 주지 못하게 하는 절차적 잠금이며, 화면에 기준
// 정보가 없어 세 조건이 동일하다.
//
// 결정 상태 4범주: 최종 선택(상품 1개) / 후보만 남김(2개 이상) / 더 탐색하고
// 싶음 / 적합한 상품 없음(이유). 후보 ID까지 기록해야 필수 조건 위반·선택-거절
// 쌍 분석에서 shortlist 참가자가 빠지지 않는다.
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

export type FinalStatus = "final" | "shortlist" | "explore_more" | "none_suitable";

export type FinalChoicePayload = {
  status: FinalStatus;
  productId?: string | null;
  shortlistIds?: string[];
  noneReason?: string;
};

/** 처음부터 펼쳐 보여줄 상품 수 — 긴 세션(노출 수십 개)에서 목록이 압도하지 않게.
 *  입력은 구매→좋아요→최근 순으로 정렬돼 오므로, 접히는 건 오래전에 본 무반응 상품뿐이다. */
const VISIBLE_CAP = 20;

const STATUS_OPTIONS: { value: FinalStatus; ko: string; en: string }[] = [
  { value: "final", ko: "하나의 상품을 최종 선택했다", en: "I made a final choice of one product" },
  { value: "shortlist", ko: "두 개 이상의 후보만 남겼다", en: "I narrowed it down to two or more candidates" },
  { value: "explore_more", ko: "아직 더 탐색하고 싶다", en: "I still want to explore more" },
  { value: "none_suitable", ko: "현재 추천 중에는 적합한 상품이 없다", en: "None of the recommended products fit my needs" },
];

export default function FinalChoiceModal({
  products,
  submitting = false,
  onConfirm,
}: {
  products: SeenProduct[];
  submitting?: boolean;
  onConfirm: (payload: FinalChoicePayload) => void;
}) {
  const [status, setStatus] = useState<FinalStatus | null>(null);
  // 대화 중 '구매'를 누른 상품이 있으면 최종 선택의 기본값으로 — 가장 강한 선택 신호.
  const [picked, setPicked] = useState<string | null>(
    () => products.find((p) => p.purchased)?.productId ?? null,
  );
  const [shortlist, setShortlist] = useState<string[]>([]);
  const [noneReason, setNoneReason] = useState("");
  const [showAll, setShowAll] = useState(false);

  const visible = showAll ? products : products.slice(0, VISIBLE_CAP);
  const hidden = products.length - VISIBLE_CAP;
  const needsList = status === "final" || status === "shortlist";
  const canSubmit =
    status === "final" ? picked !== null :
    status === "shortlist" ? shortlist.length >= 2 :
    status === "none_suitable" ? noneReason.trim().length > 0 :
    status === "explore_more";

  const toggleShortlist = (id: string) =>
    setShortlist((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const submit = () => {
    if (!status || !canSubmit) return;
    onConfirm({
      status,
      productId: status === "final" ? picked : null,
      shortlistIds: status === "shortlist" ? shortlist : [],
      noneReason: status === "none_suitable" ? noneReason.trim() : undefined,
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="card flex max-h-[88dvh] w-full max-w-2xl flex-col p-5">
        <h2 className="text-base font-bold text-[#191919]">
          {tr("마치기 전에, 현재 결정 상태를 알려주세요", "Before Finishing, Tell Us Where You Stand")}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-[#5f6368]">
          {tr("이 쇼핑 과제의 결정 상태를 선택해 주세요. 확정 후에는 바꿀 수 없어요.", "Select the state of your decision for this shopping task. You cannot change it after confirming.")}
        </p>

        {/* 결정 상태 4범주 */}
        <div className="mt-3 space-y-1.5">
          {STATUS_OPTIONS.map((o) => {
            const on = status === o.value;
            return (
              <button
                key={o.value}
                onClick={() => setStatus(o.value)}
                aria-pressed={on}
                className={`block w-full rounded-xl border px-4 py-2.5 text-left text-xs font-medium transition-[color,background-color,border-color] duration-150 ${
                  on ? "border-[#4f46e5] bg-[#eef2ff] text-[#4f46e5]" : "border-[#e4e8eb] text-[#404040] hover:border-[#4f46e5]"
                }`}
              >
                {tr(o.ko, o.en)}
              </button>
            );
          })}
        </div>

        {/* 상품 목록 — 최종 선택(단일) / 후보(다중 체크) */}
        {needsList && (
          <div className="mt-3 min-h-0 flex-1 space-y-1.5 overflow-y-auto border-t border-[#f0f2f4] pr-1 pt-3">
            <p className="text-[11px] font-semibold text-[#9aa0a6]">
              {status === "final"
                ? tr("실제로 산다면 고를 하나를 선택해 주세요.", "Choose the one product you would purchase.")
                : tr("남긴 후보를 모두 선택해 주세요 (2개 이상).", "Select all remaining candidates (two or more).")}
            </p>
            {visible.map((p) => {
              const on = status === "final" ? picked === p.productId : shortlist.includes(p.productId);
              return (
                <button
                  key={p.productId}
                  onClick={() => (status === "final" ? setPicked(p.productId) : toggleShortlist(p.productId))}
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
                    } ${status === "shortlist" ? "rounded-md" : ""}`}
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
        )}

        {status === "none_suitable" && (
          <textarea
            value={noneReason}
            onChange={(e) => setNoneReason(e.target.value)}
            autoFocus
            rows={2}
            placeholder={tr("어떤 점이 맞지 않았는지 알려주세요 (예: 원하는 색상이 없었어요)", "Please tell us what did not fit your needs (for example, the color you wanted was unavailable).")}
            className="mt-3 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs leading-relaxed focus:border-[#4f46e5] focus:outline-none"
          />
        )}

        <button
          onClick={submit}
          disabled={!canSubmit || submitting}
          className="btn btn-primary mt-3 w-full py-2.5 text-sm"
        >
          {submitting ? tr("저장하는 중…", "Saving…") : tr("이 상태로 확정", "Confirm")}
        </button>
      </div>
    </div>
  );
}
