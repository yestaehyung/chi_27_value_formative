"use client";

import { useLayoutEffect, useRef, useState } from "react";

// 네이버 AI 쇼핑 스타일 입력창 (리디자인 후보). 2행 레이아웃:
//  [ textarea (placeholder) ]
//  [ 좌측 아이콘 ............... 원형 전송/정지 버튼 ]
// 색은 ValueCommit 인디고(#4F46E5) 유지 — 네이버 파랑/그린 아님 (CLAUDE.md 설계원칙).
export default function ChatComposer({
  onSend,
  disabled,
  loading,
  onStop,
  placeholder = "무엇이든 물어보세요",
  disclaimer = true,
  suggestions,
  value,
  onChange,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  loading?: boolean;
  onStop?: () => void;
  placeholder?: string;
  disclaimer?: boolean;
  suggestions?: string[];
  // controlled 모드 (옵션): value/onChange를 주면 외부가 입력값 제어 (예: 칩 클릭 → 입력창 채우기).
  // 안 주면 내부 state 사용 (기존 동작).
  value?: string;
  onChange?: (v: string) => void;
}) {
  const [inner, setInner] = useState("");
  const text = value !== undefined ? value : inner;
  const setText = (v: string) => (onChange ? onChange(v) : setInner(v));
  const canSend = !!text.trim() && !disabled && !loading;

  // textarea 자동 높이 — 내용에 맞춰 박스가 커진다 (max-h까지, 넘으면 스크롤).
  const taRef = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [text]);

  const submit = () => {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  };

  // 브랜드색은 CSS 변수 --brand 사용 (미리보기에서 인디고↔네이버파랑 토글). 미설정 시 인디고.
  const brand = "var(--brand, #4f46e5)";
  const brandHover = "var(--brand-hover, #4338ca)";

  return (
    <div>
    {/* 답변 칩 — 입력창 위 (백엔드 동적 생성 또는 시나리오 기반). 클릭 시 입력창에 채움(전송 X) → 사용자가 보고 다듬어 전송. */}
    {suggestions && suggestions.length > 0 && !loading && (
      <div className="mb-2 flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => setText(s)}
            disabled={disabled}
            className="rounded-full border border-[#e4e8eb] bg-white px-3 py-1.5 text-[12px] text-[#5f6368] transition-colors duration-150 hover:bg-[#f5f6f8] active:scale-[0.96] disabled:opacity-50"
            style={{ ["--tw-text-opacity" as string]: "1" }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = brand; e.currentTarget.style.color = brand; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#e4e8eb"; e.currentTarget.style.color = "#5f6368"; }}
          >
            {s}
          </button>
        ))}
      </div>
    )}
    <div
      className="rounded-[20px] border border-[#e4e8eb] bg-white px-4 pb-2.5 pt-3.5 shadow-[0_1px_2px_rgba(0,0,0,0.03),0_8px_24px_-12px_rgba(0,0,0,0.08)] transition-colors duration-150"
      style={{ ["--tw-ring-color" as string]: brand }}
      onFocusCapture={(e) => (e.currentTarget.style.borderColor = brand)}
      onBlurCapture={(e) => (e.currentTarget.style.borderColor = "#e4e8eb")}
    >
      <textarea
        ref={taRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder={placeholder}
        disabled={disabled}
        className="block max-h-40 min-h-[1.75rem] w-full resize-none overflow-y-auto bg-transparent text-[15px] leading-relaxed text-[#191919] placeholder:text-[#b0b8c1] focus:outline-none"
      />
      <div className="mt-1 flex items-center justify-end">
        {loading ? (
          <button
            onClick={onStop}
            aria-label="중지"
            style={{ backgroundColor: brand }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = brandHover)}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = brand)}
            className="flex h-10 w-10 items-center justify-center rounded-full text-white transition-[scale] duration-150 active:scale-[0.92]"
          >
            <span className="block h-3 w-3 rounded-[3px] bg-white" />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            aria-label="전송"
            style={canSend ? { backgroundColor: brand } : { backgroundColor: "#e4e8eb", color: "#b0b8c1" }}
            onMouseEnter={(e) => canSend && (e.currentTarget.style.backgroundColor = brandHover)}
            onMouseLeave={(e) => canSend && (e.currentTarget.style.backgroundColor = brand)}
            className="flex h-10 w-10 items-center justify-center rounded-full text-white transition-[scale] duration-150 enabled:active:scale-[0.92]"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="19" x2="12" y2="5" /><polyline points="6 11 12 5 18 11" />
            </svg>
          </button>
        )}
      </div>
    </div>
    {disclaimer && (
      <p className="mt-2 text-center text-[11px] text-[#b0b8c1]">
        AI 답변으로 정확하지 않은 정보가 포함될 수 있어요.
      </p>
    )}
    </div>
  );
}
