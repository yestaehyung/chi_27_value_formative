"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function ResearchSmePage() {
  const [insights, setInsights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.smeInsights()
      .then((d) => setInsights(d.insights))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">SME Insight 번역</h1>
          <p className="mt-1 text-sm text-[#606060]">
            세션들에서 집계된 hidden intention을 판매자(SME)가 실행할 수 있는 전략으로 번역합니다.
            개인 추론이 아니라 집계 패턴 수준의 제안입니다 (이론모듈 Module J).
          </p>
        </div>
        <Link href="/research/ontology" className="btn">Hybrid Ontology →</Link>
      </div>

      {loading && <div className="card p-8 text-center text-sm text-[#9aa0a6]">집계 및 번역 중…</div>}

      <div className="grid gap-4 md:grid-cols-2">
        {!loading && insights.length === 0 && (
          <div className="card col-span-2 p-8 text-center text-sm text-[#9aa0a6]">
            아직 관찰된 hidden intention이 없어요. 세션이나 시뮬레이션을 먼저 실행하세요.
          </div>
        )}
        {insights.map((ins) => (
          <div key={ins.concept.id} className="card p-5">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-sm font-bold text-[#191919]">{ins.concept.label}</h2>
              <span className="whitespace-nowrap rounded bg-[#ecfdf5] px-2 py-0.5 text-[10px] font-semibold text-[#047857]">
                관찰 {ins.linkedTopicCount}회
              </span>
            </div>
            {ins.concept.description && (
              <p className="mt-1 text-xs text-[#9aa0a6]">{ins.concept.description}</p>
            )}

            {ins.exampleTopics?.length > 0 && (
              <div className="mt-2.5 rounded-xl bg-[#f5f6f8] p-2.5 text-[11px] text-[#606060]">
                <span className="font-semibold text-[#787c82]">소비자 신호 예: </span>
                {ins.exampleTopics.join(" · ")}
              </div>
            )}

            <div className="mt-3">
              <div className="text-[11px] font-bold text-[#4f46e5]">SME 액션</div>
              <ul className="mt-1 space-y-1 text-xs text-[#404040]">
                {(ins.concept.smeTranslation ?? []).map((a: string, i: number) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-[#4f46e5]">✓</span> {a}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
