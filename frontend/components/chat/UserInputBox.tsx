"use client";

import { useState } from "react";

const DEFAULT_SUGGESTIONS = [
  "운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.",
  "가능하면 저렴한 게 좋아요.",
  "오래 써도 괜찮은 건 어느 쪽일까요? 한달 사용 리뷰가 궁금해요.",
];

export default function UserInputBox({
  onSend,
  disabled,
  suggestions,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
  suggestions?: string[];
}) {
  const [text, setText] = useState("");
  const SUGGESTIONS = suggestions?.length ? suggestions : DEFAULT_SUGGESTIONS;

  const submit = () => {
    const t = text.trim();
    if (!t || disabled) return;
    onSend(t);
    setText("");
  };

  return (
    <div className="border-t border-[#f0f2f4] p-3">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setText(s)}
            className="rounded-full border border-[#e4e8eb] bg-white px-3 py-1.5 text-[11px] text-[#606060] transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] active:scale-[0.96]"
          >
            {s.length > 28 ? s.slice(0, 28) + "…" : s}
          </button>
        ))}
      </div>
      <div className="chat-input flex items-end gap-2 px-3.5 py-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          rows={1}
          placeholder="무엇을 찾고 계세요? (Enter로 전송)"
          className="max-h-32 min-h-[2.25rem] flex-1 resize-none bg-transparent py-1.5 text-sm leading-relaxed placeholder:text-[#b0b8c1] focus:outline-none"
          disabled={disabled}
        />
        <button
          onClick={submit}
          disabled={disabled || !text.trim()}
          aria-label="전송"
          className="mb-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#4f46e5] text-white hover:bg-[#4338ca] disabled:bg-[#e4e8eb] disabled:text-[#b0b8c1] enabled:active:scale-[0.96]"
          style={{ transitionProperty: "background-color, scale", transitionDuration: "150ms" }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
