"use client";

// 데모 시작 화면 — 상품 풀과 추천 품질을 눈으로 확인하는 용도.
//
// 본실험 흐름(설문 → 튜토리얼 → 조건 배정 → 과제 순서)을 전부 건너뛴다. 세션은 mode="demo"로
// 만들어져서 조건 배정을 받지 않고 조건 균형 집계에도 안 잡힌다 — 데모를 아무리 돌려도
// 실험 데이터가 오염되지 않는다.
//
// study 모드 배포에서도 열린다 (middleware matcher에 없음).
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import ChatComposer from "@/components/chat/ChatComposer";
import { api } from "@/lib/api";
import type { Scenario } from "@/lib/types";

type PoolRow = { category: string; count: number };

export default function DemoStartPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [pool, setPool] = useState<{ total: number; categories: PoolRow[] } | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [poolOpen, setPoolOpen] = useState(false);

  useEffect(() => {
    api.scenarios().then((d) => setScenarios(d.scenarios ?? [])).catch(console.error);
    api.productPoolSummary().then(setPool).catch(console.error);
  }, []);

  const start = async (scenarioId: string, custom?: { title?: string; context?: string }, first?: string) => {
    if (creating) return;
    setCreating(true);
    setError(null);
    try {
      const res = await api.createSession(scenarioId, "ours", custom, undefined, "demo");
      if (first) sessionStorage.setItem(`vc_first_${res.sessionId}`, first);
      router.push(`/demo/${res.sessionId}`);
    } catch (e) {
      console.error(e);
      setError("세션을 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
      setCreating(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="flex items-baseline justify-between gap-3">
        <h1 className="text-xl font-bold text-[#191919]">데모 — 추천 확인</h1>
        <span className="rounded-full bg-[#eef2ff] px-2.5 py-1 text-[11px] font-semibold text-[#4f46e5]">
          실험 데이터와 분리됨
        </span>
      </div>
      <p className="mt-1.5 text-sm leading-relaxed text-slate-500">
        설문·튜토리얼 없이 바로 대화합니다. 여기서 만든 세션은 <code className="rounded bg-[#f4f5f7] px-1">mode=demo</code>라
        조건 배정과 집계에서 제외돼요.
      </p>

      {/* 상품 풀 — "새 상품이 실제로 DB에 들어왔나"를 바로 확인 */}
      {pool && (
        <div className="mt-5 rounded-xl border border-[#e4e8eb] bg-white p-4">
          <button
            onClick={() => setPoolOpen((v) => !v)}
            className="flex w-full items-center justify-between gap-2 text-left"
          >
            <span className="text-sm font-semibold text-[#191919]">
              현재 상품 풀{" "}
              <span className="tabular-nums text-[#4f46e5]">{pool.total.toLocaleString()}</span>개
              <span className="ml-1.5 font-normal text-slate-400">
                · 카테고리 {pool.categories.length}종
              </span>
            </span>
            <span className="shrink-0 text-xs text-slate-400">{poolOpen ? "접기 ▴" : "펼치기 ▾"}</span>
          </button>
          {poolOpen && (
            <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 border-t border-[#f0f2f4] pt-3 sm:grid-cols-3">
              {pool.categories.map((c) => (
                <div key={c.category} className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="truncate text-slate-600">{c.category}</span>
                  <span className="shrink-0 tabular-nums text-slate-400">{c.count.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}
          <p className="mt-2 text-[11px] leading-relaxed text-slate-400">
            DB 기준 집계입니다. 시드 파일을 바꿔도 기존 상품이 있으면 시딩을 건너뛰므로,
            새 상품 반영에는 <code className="rounded bg-[#f4f5f7] px-1">VC_SEED_UPSERT=1</code> 1회 배포가 필요해요.
          </p>
        </div>
      )}

      <div className="mt-6">
        <ChatComposer
          onSend={(msg) => start("custom", { title: "데모", context: msg }, msg)}
          disabled={creating}
          loading={creating}
          placeholder="무엇을 찾고 계세요? (예: 캠핑에서 쓸 블루투스 스피커)"
        />
      </div>

      {scenarios.length > 0 && (
        <>
          <div className="mt-6 text-xs font-semibold text-slate-400">또는 시나리오로 시작</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {scenarios.map((sc) => (
              <button
                key={sc.id}
                onClick={() => start(sc.id, undefined, sc.initialUserNeed || undefined)}
                disabled={creating}
                className="rounded-full border border-[#e4e8eb] bg-white px-4 py-2 text-sm text-[#404040] transition-[color,border-color,transform] duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] active:scale-[0.98] disabled:opacity-40"
              >
                {sc.title}
                {sc.targetCategory && (
                  <span className="ml-1.5 text-xs text-slate-400">{sc.targetCategory}</span>
                )}
              </button>
            ))}
          </div>
        </>
      )}

      {error && <p className="mt-4 text-sm font-semibold text-rose-600">{error}</p>}
    </div>
  );
}
