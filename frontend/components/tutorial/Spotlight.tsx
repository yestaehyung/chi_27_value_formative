"use client";

import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

export type SpotStep = { selector: string; title: string; body: string };

const TIP_W = 320;
const PAD = 8;

// 가벼운 커스텀 코치마크 — 타깃을 box-shadow로 도려내 하이라이트하고 툴팁을 띄운다.
// 외부 라이브러리 없음. 타깃은 selector(예: '[data-tutorial="radars"]')로 찾는다.
export default function Spotlight({
  steps,
  onDone,
  onSkip,
}: {
  steps: SpotStep[];
  onDone: () => void;
  onSkip?: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => setMounted(true), []);

  const remeasure = useCallback(() => {
    const el = steps[i] ? document.querySelector(steps[i].selector) : null;
    setRect(el ? el.getBoundingClientRect() : null);
  }, [i, steps]);

  // 단계 바뀌면 타깃을 화면 중앙으로 스크롤 후 측정 (스크롤 정착 대기)
  useEffect(() => {
    if (!mounted) return;
    const el = steps[i] ? document.querySelector(steps[i].selector) : null;
    if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
    remeasure();
    const t = window.setTimeout(remeasure, 340);
    return () => window.clearTimeout(t);
  }, [mounted, i, steps, remeasure]);

  // 리사이즈/스크롤 시 위치 추적
  useEffect(() => {
    if (!mounted) return;
    window.addEventListener("resize", remeasure);
    window.addEventListener("scroll", remeasure, true);
    return () => {
      window.removeEventListener("resize", remeasure);
      window.removeEventListener("scroll", remeasure, true);
    };
  }, [mounted, remeasure]);

  if (!mounted || steps.length === 0) return null;

  const step = steps[i];
  const last = i === steps.length - 1;
  const skip = () => (onSkip ? onSkip() : onDone());

  const box = rect
    ? { top: rect.top - PAD, left: rect.left - PAD, width: rect.width + PAD * 2, height: rect.height + PAD * 2 }
    : null;

  // 툴팁 위치: 아래 공간 있으면 아래 → 위 → (타깃이 크면) 공간 넓은 옆.
  let tipStyle: CSSProperties = { top: "50%", left: "50%", transform: "translate(-50%, -50%)" };
  if (box) {
    const M = 12;
    const EST_H = 180; // 툴팁 대략 높이 (옆/위 배치 시 화면 밖 방지용)
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const clampX = (x: number) => Math.min(Math.max(M, x), vw - TIP_W - M);
    const centerX = clampX(box.left + box.width / 2 - TIP_W / 2);
    const belowRoom = vh - (box.top + box.height);
    const aboveRoom = box.top;
    const tall = box.height > vh * 0.55; // 타깃이 화면 절반 넘게 길면 옆에

    if (!tall && belowRoom > EST_H + M) {
      tipStyle = { top: box.top + box.height + M, left: centerX };
    } else if (!tall && aboveRoom > EST_H + M) {
      tipStyle = { top: box.top - M, left: centerX, transform: "translateY(-100%)" };
    } else {
      // 옆 배치 — 공간이 더 넓은 쪽, 세로 중앙 정렬(화면 안으로 clamp)
      const midY = Math.min(Math.max(box.top + box.height / 2, EST_H / 2 + M), vh - EST_H / 2 - M);
      const toLeft = box.left >= vw - (box.left + box.width);
      tipStyle = toLeft
        ? { top: midY, left: Math.max(M, box.left - TIP_W - M), transform: "translateY(-50%)" }
        : { top: midY, left: Math.min(vw - TIP_W - M, box.left + box.width + M), transform: "translateY(-50%)" };
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-[100]">
      {box ? (
        <div
          className="pointer-events-none absolute rounded-xl ring-2 ring-[#4f46e5] duration-200"
          style={{
            top: box.top,
            left: box.left,
            width: box.width,
            height: box.height,
            boxShadow: "0 0 0 9999px rgba(17,17,17,0.55)",
            transitionProperty: "top, left, width, height",
            transitionTimingFunction: "cubic-bezier(0.2, 0, 0, 1)",
          }}
        />
      ) : (
        <div className="absolute inset-0 bg-black/55" />
      )}

      {/* 위치 래퍼(transform=배치) ⟂ 애니메이션 박스(transform=scale) 분리 —
          한 엘리먼트에 둘 다 주면 transform이 충돌해 위치가 틀어진다. */}
      <div className="absolute w-[320px]" style={tipStyle}>
        <div key={i} className="tip-in rounded-2xl bg-white p-4 shadow-xl">
        <div className="text-[11px] font-semibold tabular-nums text-[#4f46e5]">
          {i + 1} / {steps.length}
        </div>
        <h3 className="mt-1 text-sm font-bold text-[#191919]">{step.title}</h3>
        <p className="mt-1.5 whitespace-pre-line text-[13px] leading-relaxed text-[#404040]">{step.body}</p>
        <div className="mt-3 flex items-center justify-between">
          <button className="-ml-1.5 rounded px-1.5 py-1 text-[11px] text-[#9aa0a6] transition-colors duration-150 hover:text-[#606060] active:scale-[0.96]" onClick={skip}>
            건너뛰기
          </button>
          <div className="flex gap-2">
            {i > 0 && (
              <button className="btn px-3 py-1.5 text-xs" onClick={() => setI(i - 1)}>
                이전
              </button>
            )}
            <button className="btn btn-primary px-3 py-1.5 text-xs" onClick={() => (last ? onDone() : setI(i + 1))}>
              {last ? "시작하기" : "다음"}
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
