"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Pair } from "@/lib/types";

export default function ResearchPairsPage() {
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [mining, setMining] = useState(false);
  const [miningMsg, setMiningMsg] = useState<string | null>(null);

  const load = () => api.pairs().then((d) => setPairs(d.pairs)).catch(console.error);
  useEffect(() => { load(); }, []);

  const runMining = async () => {
    setMining(true);
    setMiningMsg(null);
    try {
      const res = await api.runPairMining(5);
      if (res.features.length === 0) {
        setMiningMsg(`pair ${res.pairCount}개 — 후보 feature 없음 (minPairs=${res.minPairs} 필요)`);
      } else {
        setMiningMsg(`pair ${res.pairCount}개에서 feature 후보 ${res.features.length}개 발견 → Discovered Features 페이지에서 검토하세요`);
      }
    } catch (e) {
      console.error(e);
      setMiningMsg("mining 실패");
    } finally {
      setMining(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Chosen-Rejected Pairs</h1>
          <p className="mt-1 text-sm text-slate-500">
            WIMHF 관점: 무엇이 선택을 갈랐는가? 같은 추천 turn 안의 like/dislike·purchase/ignored에서 자동 생성됩니다.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/research/features" className="btn">Features →</Link>
          <button onClick={runMining} disabled={mining || pairs.length === 0} className="btn btn-primary">
            {mining ? "mining…" : "⛏ Pair Mining 실행"}
          </button>
        </div>
      </div>
      {miningMsg && <div className="rounded-lg bg-indigo-50 px-3 py-2 text-xs text-indigo-700">{miningMsg}</div>}

      <div className="space-y-3">
        {pairs.length === 0 && (
          <div className="card p-8 text-center text-sm text-slate-400">
            아직 pair가 없어요. 세션에서 좋아요/싫어요를 남기거나 시뮬레이션을 실행하세요.
          </div>
        )}
        {pairs.map((p) => (
          <div key={p.id} className="card p-4 text-xs">
            <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{p.labelSource}</span>
              <Link href={`/research/session/${p.sessionId}`} className="font-mono text-emerald-600 hover:underline">
                {p.sessionId}
              </Link>
              <span>· {p.promptContext}</span>
            </div>
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2.5">
                <div className="text-[10px] font-bold text-emerald-600">CHOSEN</div>
                <div className="mt-0.5 font-medium">{p.chosenProduct?.title}</div>
                <div className="mt-0.5 text-slate-500">
                  {p.chosenProduct?.price.toLocaleString()}원 · 한달리뷰 {Math.round((p.chosenProduct?.longTermReviewRatio ?? 0) * 100)}% · {p.chosenProduct?.sellerGrade}
                </div>
              </div>
              <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-2.5">
                <div className="text-[10px] font-bold text-rose-600">REJECTED</div>
                <div className="mt-0.5 font-medium">{p.rejectedProduct?.title}</div>
                <div className="mt-0.5 text-slate-500">
                  {p.rejectedProduct?.price.toLocaleString()}원 · 한달리뷰 {Math.round((p.rejectedProduct?.longTermReviewRatio ?? 0) * 100)}% · {p.rejectedProduct?.sellerGrade}
                </div>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(p.productDiff.cueDifferences ?? []).map((c, i) => (
                <span key={i} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{c}</span>
              ))}
            </div>
            {p.userReasonText && <div className="mt-1.5 text-slate-600">사용자 이유: &quot;{p.userReasonText}&quot;</div>}
            <div className="mt-1 text-slate-500">{p.productDiff.naturalLanguageSummary}</div>
            {p.inferredHiddenReason && (
              <div className="mt-1.5 rounded bg-indigo-50 px-2 py-1.5 text-indigo-700">
                💡 {p.inferredHiddenReason}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
