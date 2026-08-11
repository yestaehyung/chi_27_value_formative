"use client";

import { Children, ReactNode, useEffect, useRef, useState } from "react";
import { tr } from "@/lib/studyI18n";

// ProductCard 고정폭/간격과 동기 — 카드 가시성 계산에 사용
const CARD_W = 284;
const GAP = 12; // gap-3

/**
 * 추천 카드 가로 캐러셀 — 잘린 카드(D·E)의 발견성을 보장하는 어포던스 3종:
 * 엣지 페이드(잘림 신호) + 가시성 dot 인디케이터 + 좌우 화살표.
 * 피드백이 연구의 핵심 데이터라서, 뒤쪽 카드가 안 보이면 position bias가
 * 증거 레이어에 들어간다 — 이 컴포넌트가 그 방지 장치.
 */
export default function ProductCarousel({ children }: { children: ReactNode }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewW, setViewW] = useState(0);
  const [totalW, setTotalW] = useState(0);

  const items = Children.toArray(children);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const measure = () => {
      setViewW(el.clientWidth);
      setTotalW(el.scrollWidth);
      setScrollLeft(el.scrollLeft);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [items.length]);

  const canLeft = scrollLeft > 4;
  const canRight = scrollLeft < totalW - viewW - 4;
  const hasOverflow = totalW > viewW + 4;

  // 카드 중심이 뷰포트 안에 있으면 "보이는 카드" — dot 채움 기준
  const isVisible = (i: number) => {
    const center = i * (CARD_W + GAP) + CARD_W / 2;
    return center >= scrollLeft && center <= scrollLeft + viewW;
  };

  // 1클릭 = 카드 1장 — 항목 수가 적고 카드별 피드백을 남기는 흐름이라 정밀 이동이 관례에 맞음
  const handleArrow = (dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * (CARD_W + GAP), behavior: "smooth" });
  };

  return (
    <div>
      <div className="relative">
        <div
          ref={scrollerRef}
          onScroll={(e) => setScrollLeft(e.currentTarget.scrollLeft)}
          className="flex snap-x snap-mandatory gap-3 overflow-x-auto scroll-smooth pb-2"
        >
          {items.map((child, i) => (
            <div key={i} className="w-[284px] shrink-0 snap-start">
              {child}
            </div>
          ))}
        </div>
        {/* 엣지 페이드 — "이 방향에 더 있음" 신호. 클릭은 통과(pointer-events-none) */}
        {canLeft && (
          <div className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-white to-transparent" />
        )}
        {canRight && (
          <div className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-white to-transparent" />
        )}
      </div>

      {hasOverflow && (
        <div className="mt-1 flex items-center justify-center gap-3">
          <button
            onClick={() => handleArrow(-1)}
            disabled={!canLeft}
            aria-label={tr("이전 상품 보기", "View previous product")}
            className="btn h-10 w-10 rounded-full p-0 text-base leading-none"
          >
            ‹
          </button>
          <div className="flex items-center gap-1.5" aria-hidden>
            {items.map((_, i) => (
              <span
                key={i}
                className={`h-1.5 w-1.5 rounded-full transition-colors duration-150 ${
                  isVisible(i) ? "bg-[#4f46e5]" : "bg-[#d9dde2]"
                }`}
              />
            ))}
          </div>
          <button
            onClick={() => handleArrow(1)}
            disabled={!canRight}
            aria-label={tr("다음 상품 보기", "View next product")}
            className="btn h-10 w-10 rounded-full p-0 text-base leading-none"
          >
            ›
          </button>
        </div>
      )}
    </div>
  );
}
