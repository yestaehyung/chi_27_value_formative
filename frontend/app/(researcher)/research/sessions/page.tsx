"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { SessionInfo } from "@/lib/types";

const TABS = [
  { key: "manual", label: "참가자" },
  { key: "simulation", label: "시뮬레이션" },
  { key: "pscon", label: "PSCon 분석" },
];

export default function ResearchSessionsPage() {
  const [tab, setTab] = useState("manual");
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [modeCounts, setModeCounts] = useState<Record<string, number>>({});
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<string | null>(null);
  const [ly, setLy] = useState<any>(null);
  const [participants, setParticipants] = useState<any[]>([]);
  const [selectedPid, setSelectedPid] = useState("");

  useEffect(() => {
    api.researchSessions(tab)
      .then((d) => { setSessions(d.sessions); setModeCounts(d.modeCounts || {}); })
      .catch(console.error);
    setSelectedPid(""); // 모드 바꾸면 선택 초기화
  }, [tab]);

  useEffect(() => {
    api.latentYield().then(setLy).catch(console.error);
    api.participants().then((d) => setParticipants(d.participants || [])).catch(console.error);
  }, []);

  const pmap = useMemo(
    () => Object.fromEntries((participants as any[]).map((p) => [p.id, p])),
    [participants]
  );
  // 현재 모드 세션에 등장하는 참가자 + 각자 세션 수 (세션 많은 순)
  const pidOptions = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of sessions) if (s.participantId) counts[s.participantId] = (counts[s.participantId] ?? 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [sessions]);
  const shown = selectedPid ? sessions.filter((s) => s.participantId === selectedPid) : sessions;
  const plabel = (id?: string | null) => (id ? (pmap[id]?.label || id) : "—");

  const runExport = async () => {
    setExporting(true);
    try {
      const res = await api.runExport();
      const total = Object.values(res.files as Record<string, number>).reduce((a, b) => a + b, 0);
      setExportResult(`${res.exportDir} 에 ${Object.keys(res.files).length}개 JSONL 파일 (${total} rows) export 완료`);
    } catch (e) {
      console.error(e);
      setExportResult("export 실패");
    } finally {
      setExporting(false);
    }
  };

  const renderTable = (rows: SessionInfo[]) => (
    <div className="card overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-100 bg-slate-50 text-xs text-slate-500">
          <tr>
            {["세션", "모드", "시나리오", "상태", "turns", "feedback", "topics", "conflicts", "pairs", "시작"].map((h) => (
              <th key={h} className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id} className="border-b border-slate-50 hover:bg-slate-50/50">
              <td className="px-3 py-2">
                <Link href={`/research/session/${s.id}`} className="font-mono text-xs text-emerald-700 hover:underline">{s.id}</Link>
              </td>
              <td className="px-3 py-2 text-xs">{s.mode}</td>
              <td className="px-3 py-2 text-xs">{s.scenarioId}</td>
              <td className="px-3 py-2 text-xs">
                <span className={`rounded px-1.5 py-0.5 ${s.status === "completed" ? "bg-emerald-50 text-emerald-700" : "bg-sky-50 text-sky-700"}`}>{s.status}</span>
              </td>
              <td className="px-3 py-2 text-xs">{s.turnCount}</td>
              <td className="px-3 py-2 text-xs">{s.feedbackCount}</td>
              <td className="px-3 py-2 text-xs">{s.topicCount}</td>
              <td className="px-3 py-2 text-xs">{s.conflictCount}</td>
              <td className="px-3 py-2 text-xs">{s.pairCount}</td>
              <td className="px-3 py-2 text-xs text-slate-400">{new Date(s.startedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={10} className="px-3 py-8 text-center text-sm text-slate-400">세션이 없어요.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-balance">세션 목록</h1>
        <div className="flex flex-wrap gap-2">
          <Link href="/research/surveys" className="btn">설문 응답</Link>
          <Link href="/research/pairs" className="btn">Pairs</Link>
          <Link href="/research/features" className="btn">Features</Link>
          <Link href="/research/ontology" className="btn">Hybrid Ontology</Link>
          <Link href="/research/sme" className="btn">SME Insight</Link>
          <button onClick={runExport} disabled={exporting} className="btn btn-primary">
            {exporting ? "exporting…" : "⬇ JSONL Export"}
          </button>
        </div>
      </div>
      {exportResult && <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700">{exportResult}</div>}

      {/* 모드 탭 — 실참가자 / 시뮬 / PSCon 분리 */}
      <div className="flex flex-wrap gap-1.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-[#4f46e5] text-white"
                : "border border-[#e4e8eb] bg-white text-[#606060] hover:border-[#4f46e5]"
            }`}
          >
            {t.label}
            <span className={`ml-1.5 text-xs ${tab === t.key ? "text-indigo-200" : "text-[#b0b8c1]"}`}>
              {modeCounts[t.key] ?? 0}
            </span>
          </button>
        ))}
      </div>

      {tab === "pscon" ? (
        <>
          <div className="rounded-lg bg-[#eef2ff] px-3 py-2 text-xs text-[#4338ca]">
            PSCon 분석 세션은 배치로 자동 생성됩니다 (최근 100개만 표시). 전체 결과·방사형 그래프는{" "}
            <Link href="/pscon" className="font-medium underline">PSCon 시각화</Link>에서 보세요.
          </div>
          {renderTable(sessions)}
        </>
      ) : (
        <>
          {ly && ly.totalTopics > 0 && (
            <div className="card flex flex-wrap items-center gap-x-8 gap-y-2 px-5 py-3.5 text-xs">
              <span className="font-bold text-[#191919]">Latent Yield <span className="text-[10px] font-normal text-[#b0b8c1]">참가자·시뮬</span></span>
              <span className="text-[#606060]">
                implicit/latent 비율 <b className="font-mono text-[#4f46e5]">{(ly.implicitLatentRatio * 100).toFixed(0)}%</b>
                <span className="text-[#b0b8c1]"> ({ly.implicitLatentCount}/{ly.totalTopics})</span>
              </span>
              <span className="text-[#606060]">
                사용자 확인율 <b className="font-mono text-[#4f46e5]">{(ly.latentConfirmRate * 100).toFixed(0)}%</b>
              </span>
              <span className="text-[#606060]">
                Yield <b className="font-mono text-[#4f46e5]">{ly.latentYield?.toFixed(3)}</b>
              </span>
              <span className="text-[10px] text-[#b0b8c1]">— 말하지 않은 기준을 얼마나 만들어내고 확인받는가</span>
            </div>
          )}

          {/* 참가자 중심 — 좌: 참가자 목록 · 우: 선택한 참가자의 세션 */}
          <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
            <div className="card h-fit p-2">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="text-xs font-semibold text-[#606060]">참가자</span>
                <span className="text-[10px] text-[#b0b8c1]">{pidOptions.length}명</span>
              </div>
              <div className="max-h-[64vh] space-y-1 overflow-y-auto">
                {pidOptions.map(([id, n]) => {
                  const sel = selectedPid === id;
                  const p = pmap[id];
                  return (
                    <button
                      key={id}
                      onClick={() => setSelectedPid(sel ? "" : id)}
                      className={`flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left transition-colors active:scale-[0.99] ${
                        sel ? "bg-[#eef2ff] ring-1 ring-[#4f46e5]" : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="truncate text-xs font-medium text-[#191919]">{p?.label || id}</div>
                        <div className="truncate font-mono text-[10px] text-[#b0b8c1]">{id}</div>
                      </div>
                      <div className="flex shrink-0 items-center gap-1">
                        {p?.hasSurvey && <span className="rounded bg-emerald-50 px-1 py-0.5 text-[9px] font-medium text-emerald-700">설문</span>}
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${sel ? "bg-[#4f46e5] text-white" : "bg-slate-100 text-[#606060]"}`}>{n}</span>
                      </div>
                    </button>
                  );
                })}
                {pidOptions.length === 0 && (
                  <div className="px-2 py-8 text-center text-xs text-[#b0b8c1]">참가자가 없어요.</div>
                )}
              </div>
            </div>

            <div className="min-w-0">
              {!selectedPid ? (
                <div className="card flex min-h-[200px] items-center justify-center p-10 text-center text-sm text-[#9aa0a6]">
                  ← 왼쪽에서 참가자를 선택하면 그 사람의 세션이 보입니다.
                </div>
              ) : (
                <div className="space-y-2">
                  <div className="flex items-center justify-between px-0.5">
                    <div className="text-sm font-bold text-[#191919]">
                      {plabel(selectedPid)}
                      <span className="font-normal text-[#9aa0a6]"> · {shown.length}세션</span>
                      {pmap[selectedPid]?.hasSurvey && (
                        <Link href="/research/surveys" className="ml-2 text-xs font-normal text-emerald-600 hover:underline">설문 보기 →</Link>
                      )}
                    </div>
                    <button onClick={() => setSelectedPid("")} className="text-xs text-[#9aa0a6] transition-colors hover:text-[#4f46e5]">✕ 선택 해제</button>
                  </div>
                  {renderTable(shown)}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
