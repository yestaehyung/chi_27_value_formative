"use client";

// 한 페이지 토글 비교 (2026-07-16) — 같은 세션을 버튼으로 전환하며 여섯 UI로 본다.
// "지금 버전"은 기존 세션 페이지 컴포넌트를 무수정 import (같은 [sessionId] 세그먼트
// 아래라 그 안의 useParams()가 그대로 동작). 탭 전환 시 key로 리마운트 → 세션을
// 다시 불러오므로, 한 UI에서 대화한 내용이 다른 UI로 넘어갈 때 자동 동기화된다.

import { useState } from "react";
import { useParams } from "next/navigation";
import CurrentSessionPage from "@/components/study/CurrentStudySession";
import VariantSession, { UiVariant } from "@/components/study/VariantSession";

const TABS: { key: "current" | UiVariant; label: string; desc: string }[] = [
  { key: "current", label: "지금 버전", desc: "사이드 패널 + 칩 버튼 + 레이더" },
  { key: "a", label: "수정안 1 — 채팅 인라인", desc: "패널 없음 · 외재화가 대화 문장 안에" },
  { key: "b", label: "수정안 2 — 채팅 + 접힌 요약", desc: "인라인 + 입력창 위 기준 앵커" },
  { key: "c", label: "수정안 3 — 경량 패널", desc: "현재 디자인 그대로, 그래프·중요도·수정만 제거 + 우선순위 번호" },
  { key: "d", label: "수정안 D — 솔리드 카드 확인", desc: "단일 컬럼 · 각 기준을 맞아요로 확인하거나 달라요로 바로 수정" },
  { key: "e", label: "수정안 E — 에이전트 능동 질문", desc: "독립 질문 턴 기준 확인 · conflict 발화+옵션칩" },
];

export default function SessionComparePage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [tab, setTab] = useState<"current" | UiVariant>("current");
  const active = TABS.find((t) => t.key === tab)!;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded-xl border border-[#e4e8eb] bg-white p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`rounded-lg px-3 py-1.5 text-xs transition-colors ${
                tab === t.key
                  ? "bg-[#4f46e5] font-semibold text-white"
                  : "text-[#5f6368] hover:bg-[#f5f6f8]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <span className="text-[11px] text-[#9aa0a6]">{active.desc}</span>
        <span className="ml-auto font-mono text-[10px] text-[#c2c7cd]">{sessionId}</span>
      </div>

      {/* key=tab — 전환마다 리마운트해 서버 상태로 재동기화 */}
      <div key={tab}>
        {tab === "current" ? (
          <CurrentSessionPage />
        ) : (
          <VariantSession sessionId={sessionId} variant={tab} />
        )}
      </div>
    </div>
  );
}
