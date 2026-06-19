"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { DiscoveredFeature } from "@/lib/types";

const STATUS_STYLE: Record<string, string> = {
  candidate: "bg-amber-50 text-amber-700",
  researcher_approved: "bg-sky-50 text-sky-700",
  merged_into_concept: "bg-emerald-50 text-emerald-700",
  rejected: "bg-slate-100 text-slate-500",
};

export default function ResearchFeaturesPage() {
  const [features, setFeatures] = useState<DiscoveredFeature[]>([]);
  const [clusters, setClusters] = useState<any[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () =>
    api.features().then((d) => { setFeatures(d.features); setClusters(d.clusters ?? []); }).catch(console.error);
  useEffect(() => { load(); }, []);

  const setStatus = async (id: string, status: string) => {
    try {
      const res = await api.setFeatureStatus(id, status);
      if (res.concept) {
        setMsg(`"${res.feature.label}" → concept "${res.concept.label}" 로 ontology에 편입됨 (created_by: wimhf)`);
      }
      load();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">WIMHF-style Discovered Features</h1>
          <p className="mt-1 text-sm text-slate-500">
            chosen-rejected pair에서 bottom-up으로 발견된 hidden intention 축 후보.
            승인하면 ontology concept으로 편입됩니다.
          </p>
        </div>
        <Link href="/research/pairs" className="btn">← Pairs</Link>
      </div>
      {msg && <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{msg}</div>}

      {clusters.length > 0 && (
        <section className="card p-5">
          <h2 className="text-sm font-bold text-[#191919]">Feature Clusters (상위 가치 묶음)</h2>
          <p className="mt-1 text-xs text-[#9aa0a6]">여러 pair에서 반복된 feature들이 공유하는 상위 hidden intention입니다.</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {clusters.map((c) => (
              <div key={c.id} className="rounded-xl border border-[#e4e8eb] p-3.5">
                <div className="text-sm font-bold text-[#4f46e5]">{c.label}</div>
                <p className="mt-1 text-xs text-[#606060]">{c.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.memberFeatureLabels.map((m: string) => (
                    <span key={m} className="rounded-full bg-[#f5f6f8] px-2 py-0.5 text-[10px] text-[#606060]">{m}</span>
                  ))}
                </div>
                <div className="mt-1.5 text-[10px] text-[#9aa0a6]">
                  시나리오 분포: {Object.entries(c.scenarioDistribution ?? {}).map(([k, v]) => `${k}=${v}`).join(", ") || "–"}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {features.length === 0 && (
          <div className="card col-span-2 p-8 text-center text-sm text-slate-400">
            아직 발견된 feature가 없어요. Pairs 페이지에서 Pair Mining을 실행하세요.
          </div>
        )}
        {features.map((f) => (
          <div key={f.id} className="card p-4">
            <div className="flex items-start justify-between gap-2">
              <h2 className="text-sm font-bold">{f.label}</h2>
              <span className={`whitespace-nowrap rounded px-1.5 py-0.5 text-[10px] font-medium ${STATUS_STYLE[f.status]}`}>
                {f.status}
              </span>
            </div>
            <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{f.description}</p>

            <div className="mt-3 grid grid-cols-4 gap-1.5 text-center text-[10px]">
              {[
                ["coverage", f.coverageScore],
                ["predictive", f.predictivenessScore],
                ["novelty", f.noveltyScore],
                ["interpret", f.interpretabilityScore],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded bg-slate-50 py-1.5">
                  <div className="font-mono text-xs font-bold text-slate-700">{(v as number)?.toFixed(2) ?? "–"}</div>
                  <div className="text-slate-400">{k}</div>
                </div>
              ))}
            </div>

            <div className="mt-2 flex flex-wrap gap-1">
              {f.candidateAnchorMappings.map((a, i) => (
                <span key={i} className="rounded bg-orange-50 px-1.5 py-0.5 text-[10px] text-orange-700">
                  {a.anchor} {a.score}
                </span>
              ))}
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                {f.suggestedOntologyAction}
              </span>
            </div>

            <div className="mt-2 text-[11px] text-slate-400">
              근거 pair {f.sourcePairIds.length}개
              {f.examplePairs[0] && <> — 예: {f.examplePairs[0].shortExplanation}</>}
            </div>

            {f.status === "candidate" && (
              <div className="mt-3 flex gap-2">
                <button className="btn btn-primary flex-1 py-1 text-xs"
                        onClick={() => setStatus(f.id, "merged_into_concept")}>
                  ✓ 승인 → concept 편입
                </button>
                <button className="btn flex-1 py-1 text-xs" onClick={() => setStatus(f.id, "rejected")}>
                  ✕ 기각
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
