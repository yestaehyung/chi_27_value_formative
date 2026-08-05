"use client";

// UI 수정안 비교 진입점 (2026-07-16) — 세션을 만들거나 기존 ID를 붙여넣으면
// 한 페이지 토글 화면(/study/session/{id}/compare)으로 이동한다.
// 거기서 버튼으로 지금 버전 ↔ 수정안 1(채팅 인라인) ↔ 수정안 2(채팅+접힌 요약) ↔ 수정안 3(경량 패널) ↔ 수정안 D(솔리드 카드) ↔ 수정안 E(에이전트 능동 질문)를 전환.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function CompareEntryPage() {
  const router = useRouter();
  const [idInput, setIdInput] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = (id: string) => router.push(`/study/session/${id}/compare`);

  const newSession = async () => {
    setCreating(true);
    setError(null);
    try {
      const r = await api.createSession("custom", "ours", { title: "UI 수정안 비교", context: "" });
      go(r.sessionId);
    } catch (e) {
      setError(String(e));
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-xl pt-10">
      <h1 className="text-xl font-bold text-[#191919]">UI 수정안 비교</h1>
      <p className="mt-1 text-sm text-[#606060]">
        같은 세션을 한 페이지 안에서 버튼으로 전환하며 봅니다 — 지금 버전 · 수정안 1(채팅 인라인) · 수정안 2(채팅+접힌 요약) · 수정안 3(경량 패널) · 수정안 D(솔리드 카드) · 수정안 E(에이전트 능동 질문).
      </p>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</div>
      )}

      <div className="card mt-6 space-y-4 p-6">
        <button onClick={newSession} disabled={creating} className="btn btn-primary w-full py-2.5 text-sm">
          {creating ? "생성 중…" : "새 세션 만들어 시작"}
        </button>
        <div className="flex items-center gap-2 text-[11px] text-[#b0b8c1]">
          <span className="h-px flex-1 bg-[#f0f2f4]" />또는<span className="h-px flex-1 bg-[#f0f2f4]" />
        </div>
        <div className="flex gap-2">
          <input
            value={idInput}
            onChange={(e) => setIdInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && idInput.trim() && go(idInput.trim())}
            placeholder="기존 세션 ID 붙여넣기 (sess_…) — 지난 대화를 여섯 UI로 재조명"
            className="flex-1 rounded-lg border border-[#e4e8eb] px-3 py-2 font-mono text-xs focus:border-[#4f46e5] focus:outline-none"
          />
          <button
            onClick={() => idInput.trim() && go(idInput.trim())}
            disabled={!idInput.trim()}
            className="btn px-4 py-2 text-sm disabled:opacity-40"
          >
            열기
          </button>
        </div>
      </div>

      <a
        href="/study/vdemo"
        className="mt-3 block text-center text-xs text-[#9aa0a6] transition-colors hover:text-[#4f46e5]"
      >
        안 E 위젯 데모 (더미 데이터 · 순차 확인 · 서버 무접촉) →
      </a>
    </div>
  );
}
