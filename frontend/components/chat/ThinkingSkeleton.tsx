"use client";

import { useEffect, useState } from "react";
import AgentAvatar from "./AgentAvatar";

// 네이버 AI 스타일 로딩 — 실제 파이프라인 단계를 시간 흐름에 따라 순서대로 보여줌(A안).
// steps를 주면 stepMs 간격으로 다음 단계로 넘어가되, 마지막 단계는 응답 올 때까지 머무른다
// (거짓 '완료' 방지 — 백엔드가 단계를 스트리밍하지 않으므로 타이밍은 추정, 단계명은 실제).
// steps 미지정 시 label 한 줄로 폴백.
export default function ThinkingSkeleton({
  steps,
  label = "더 나은 답변을 위해 살펴보고 있어요…",
  stepMs = 3500,
}: {
  steps?: string[];
  label?: string;
  stepMs?: number;
}) {
  const list = steps && steps.length > 0 ? steps : [label];
  const [i, setI] = useState(0);

  useEffect(() => {
    setI(0);
    if (list.length <= 1) return;
    const id = setInterval(() => {
      // 마지막 단계 직전까지만 진행 (마지막은 응답 올 때까지 유지)
      setI((prev) => (prev < list.length - 1 ? prev + 1 : prev));
    }, stepMs);
    return () => clearInterval(id);
    // list 내용이 바뀌면 처음부터 (의존성: 조인된 문자열)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.join("|"), stepMs]);

  return (
    <div className="msg-in flex gap-2.5">
      <AgentAvatar className="mt-1 h-7 w-7" />
      <div className="min-w-0 flex-1">
        {/* 단계 문구 — 바뀔 때 부드럽게 (key로 재마운트 → fade) */}
        <div key={i} className="msg-in mb-2 text-[13px] text-[#9aa0a6]">{list[i]}</div>
        <div className="space-y-2">
          <div className="skeleton-bar h-3.5 w-[88%] rounded-full" />
          <div className="skeleton-bar h-3.5 w-[94%] rounded-full" />
          <div className="skeleton-bar h-3.5 w-[60%] rounded-full" />
        </div>
      </div>
    </div>
  );
}
