"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function PsconListPage() {
  const [convs, setConvs] = useState<any[]>([]);
  const [available, setAvailable] = useState(true);
  const [query, setQuery] = useState("");

  useEffect(() => {
    api.psconConversations()
      .then((d) => { setConvs(d.conversations || []); setAvailable(d.available); })
      .catch(console.error);
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return convs;
    return convs.filter((c) =>
      [c.firstUserMessage, String(c.convId), (c.keywords || []).join(" ")]
        .some((s) => String(s || "").toLowerCase().includes(q))
    );
  }, [convs, query]);

  return (
    <div className="space-y-6">
      <div className="msg-in">
        <h1 className="text-xl font-bold text-balance">PSCon 대화 시각화</h1>
        <p className="mt-1 text-sm text-slate-500">
          PSCon 실제 쇼핑 대화 데이터셋(영어, fully-rated, 648건). 발화·명료화·추천·좋아요/싫어요가
          주석돼 있습니다 — 읽기 전용으로 그대로 시각화합니다.
        </p>
      </div>

      <div className="msg-in card flex items-center justify-between gap-3 p-4" style={{ animationDelay: "60ms" }}>
        <span className="text-sm font-semibold">
          대화 <span className="font-normal text-[#b0b8c1]">· {filtered.length}/{convs.length} · 분석됨 {convs.filter((c) => c.analyzed).length} · <span className="text-[#4f46e5]">분석 풍부순 ↓</span></span>
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="🔍 발화·키워드·ID 검색"
          className="w-64 rounded-lg border border-[#e4e8eb] px-3 py-1.5 text-sm focus:border-[#4f46e5] focus:outline-none"
        />
      </div>

      {!available && (
        <div className="card p-6 text-center text-sm text-rose-500">
          PSCon 데이터셋 파일을 찾을 수 없어요 (`../../PSCon/dataset/conversation_en_fully_rated.json`).
        </div>
      )}

      <div className="msg-in grid gap-3 sm:grid-cols-2 lg:grid-cols-3" style={{ animationDelay: "120ms" }}>
        {filtered.map((c) => (
          <Link
            key={c.convId}
            href={`/pscon/${c.convId}`}
            style={{ transitionProperty: "border-color, box-shadow", transitionDuration: "150ms" }}
            className="card group p-4 hover:-translate-y-px hover:border-[#4f46e5] hover:shadow-[0_6px_20px_-6px_rgba(79,70,229,0.25)]"
          >
            <div className="flex items-center justify-between text-[11px] tabular-nums text-[#9aa0a6]">
              <span className="font-mono">#{c.convId}</span>
              <span>{c.turnCount}턴 · 추천 {c.recommendTurns}</span>
            </div>
            <p className="mt-2 line-clamp-2 text-sm font-medium text-[#191919] group-hover:text-[#4f46e5]">
              {c.firstUserMessage || "—"}
            </p>
            <div className="mt-2 flex flex-wrap gap-1">
              {(c.keywords || []).slice(0, 4).map((k: string, i: number) => (
                <span key={i} className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[10px] text-[#606060]">{k}</span>
              ))}
            </div>
            {c.analyzed && (c.topDims || []).length > 0 && (
              <div className="mt-2 flex flex-wrap items-center gap-1">
                <span className="text-[10px] text-[#b0b8c1]">핵심 축</span>
                {(c.topDims || []).map((d: string, i: number) => (
                  <span key={i} className="rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-semibold text-[#4338ca]">{d}</span>
                ))}
              </div>
            )}
            <div className="mt-2 flex items-center gap-3 text-[11px] font-medium tabular-nums">
              <span className="text-[#047857]">👍 {c.liked}</span>
              <span className="text-[#e03131]">👎 {c.disliked}</span>
              {c.analyzed && <span className="ml-auto rounded-full bg-[#eef2ff] px-2 py-0.5 text-[10px] font-semibold text-[#4f46e5]">분석됨</span>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
