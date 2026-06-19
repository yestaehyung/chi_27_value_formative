"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  seed: "bg-[#f5f6f8] text-[#787c82]",
  observed: "bg-[#eaf4ff] text-[#0073e6]",
  candidate: "bg-[#fffbe6] text-[#8a6d00]",
  validated: "bg-[#ecfdf5] text-[#047857]",
  confirmed: "bg-[#4f46e5] text-white",
  revised: "bg-[#f3e8ff] text-[#7c3aed]",
  rejected: "bg-[#fff5f5] text-[#e03131]",
  deprecated: "bg-[#f5f6f8] text-[#b0b8c1] line-through",
};

const ORIGIN_LABEL: Record<string, string> = {
  top_down_seed: "이론(top-down)",
  llm_extraction: "대화 추출",
  bottom_up_feature: "pair 발견(bottom-up)",
  user_correction: "사용자 수정",
};

export default function ResearchOntologyPage() {
  const [concepts, setConcepts] = useState<any[]>([]);

  useEffect(() => {
    api.concepts().then((d) => setConcepts(d.concepts)).catch(console.error);
  }, []);

  const lifecycle = ["seed", "observed", "candidate", "validated", "confirmed", "revised", "rejected", "deprecated"];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Hybrid Ontology Nodes</h1>
          <p className="mt-1 text-sm text-[#606060]">
            이론 기반 seed node와 데이터 기반 발견 feature가 결합된 concept 목록입니다.
            lifecycle: Seed → Observed → Candidate → Validated → Confirmed → Revised/Deprecated
          </p>
        </div>
        <Link href="/research/sessions" className="btn">← 세션 목록</Link>
      </div>

      <div className="flex flex-wrap gap-1.5 text-[10px]">
        {lifecycle.map((s) => (
          <span key={s} className={`rounded px-2 py-0.5 font-medium ${STATUS_STYLE[s]}`}>{s}</span>
        ))}
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-[#f0f2f4] bg-[#fafbfc] text-[#787c82]">
            <tr>
              {["concept", "→ 이론 (canonical)", "lifecycle", "origin (provenance)", "version", "연결 topic", "사용자 표시 라벨", "SME 번역", "시나리오 범위"].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {concepts.map((c) => (
              <tr key={c.id} className="border-b border-[#f7f8f9] align-top hover:bg-[#fafbfc]">
                <td className="px-3 py-2.5">
                  <div className="font-semibold text-[#191919]">{c.label}</div>
                  <div className="font-mono text-[10px] text-[#b0b8c1]">{c.normalizedLabel}</div>
                  {c.description && <div className="mt-0.5 max-w-xs text-[10px] text-[#9aa0a6]">{c.description}</div>}
                </td>
                <td className="px-3 py-2.5">
                  {(c.anchorMappings ?? []).length === 0 ? (
                    <span className="text-[10px] text-[#b0b8c1]">–</span>
                  ) : (
                    <div className="flex flex-wrap gap-1">
                      {(c.anchorMappings ?? []).slice(0, 3).map((a: any) => (
                        <span key={a.anchor} className="rounded-full bg-[#eef2ff] px-1.5 py-0.5 text-[10px] text-[#4338ca]">
                          {a.anchor} {a.score.toFixed(2)}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${STATUS_STYLE[c.status] ?? STATUS_STYLE.observed}`}>
                    {c.status}
                  </span>
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex flex-wrap gap-1">
                    {(c.origin?.length ? c.origin : [c.createdBy]).map((o: string, i: number) => (
                      <span key={i} className="rounded bg-[#f5f6f8] px-1.5 py-0.5 text-[10px] text-[#606060]">
                        {ORIGIN_LABEL[o] ?? o}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono">{Number(c.version ?? 1).toFixed(1)}</td>
                <td className="px-3 py-2.5">{c.linkedTopicCount}</td>
                <td className="px-3 py-2.5 text-[#606060]">{c.userVisibleLabel ?? "–"}</td>
                <td className="px-3 py-2.5 text-[#606060]">
                  {(c.smeTranslation ?? []).slice(0, 2).map((s: string, i: number) => <div key={i}>· {s}</div>)}
                </td>
                <td className="px-3 py-2.5 text-[10px] text-[#9aa0a6]">{(c.scenarioScope ?? []).join(", ") || "전역"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
