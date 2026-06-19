"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Turn } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import OntologyGraph from "@/components/research/OntologyGraph";
import SnapshotTimeline from "@/components/research/SnapshotTimeline";
import ValueTrajectory from "@/components/research/ValueTrajectory";

const TABS = ["replay", "spec", "trajectory", "ontology", "rig", "timeline", "conflicts", "pairs", "evidence", "gap"] as const;
type Tab = (typeof TABS)[number];

export default function ResearchSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [data, setData] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [gap, setGap] = useState<any>(null);
  const [gtText, setGtText] = useState("");
  const [metaPath, setMetaPath] = useState<any>(null);
  const [predict, setPredict] = useState<any>(null);
  const [transitions, setTransitions] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("replay");

  const [spec, setSpec] = useState<any>(null);
  const loadGap = () => api.gap(sessionId).then(setGap).catch(() => {});
  useEffect(() => {
    if (!sessionId) return;
    api.sessionReplay(sessionId).then((d) => {
      setData(d);
      const pid = d?.session?.participantId;
      if (pid) api.participantSpec(pid).then(setSpec).catch(() => {});
    }).catch(console.error);
    api.valueProfile(sessionId).then(setProfile).catch(console.error);
    loadGap();
    api.rigMetaPath(sessionId).then(setMetaPath).catch(() => {});
    api.rigPredict(sessionId).then(setPredict).catch(() => {});
    api.rigTheoryTransitions().then(setTransitions).catch(() => {});
  }, [sessionId]);

  const saveGroundTruth = async () => {
    const items = gtText.split("\n").map((s) => s.trim()).filter(Boolean);
    await api.setGroundTruth(sessionId, items);
    loadGap();
  };

  if (!data) return <div className="py-20 text-center text-sm text-slate-400">불러오는 중…</div>;

  const feedbackByTurn: Record<string, any[]> = {};
  for (const f of data.feedback) (feedbackByTurn[f.turnId ?? "none"] ??= []).push(f);

  // chip 수정 이벤트를 발생 시점(turn index)별로 묶기 (S58 분석)
  const correctionsByTurnIndex: Record<number, any[]> = {};
  for (const c of data.corrections ?? []) (correctionsByTurnIndex[c.turnIndex] ??= []).push(c);
  const CORRECTION_LABEL: Record<string, string> = {
    confirm: "맞아요 확인", reject: "아니에요(거절)", increase_priority: "중요도 ↑",
    decrease_priority: "중요도 ↓", edit_label: "직접 수정",
  };
  // 관찰 마커/열람 이벤트를 turn index별로 (DG3/DG4)
  const markersByTurnIndex: Record<number, any[]> = {};
  for (const m of data.markers ?? []) (markersByTurnIndex[m.turnIndex] ??= []).push(m);
  const MARKER_LABEL: Record<string, string> = {
    trust: "🟢 신뢰", distrust: "🔴 불신", confusion: "🟡 혼란",
    correction_wish: "✏️ 수정욕구", inspect_evidence: "🔎 근거 확인", other: "기타",
  };

  const productById: Record<string, any> = {};
  for (const imp of data.impressions) if (imp.product) productById[imp.product.id] = imp.product;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">
            세션 replay <span className="font-mono text-sm font-normal text-slate-400">{sessionId}</span>
          </h1>
          <div className="mt-0.5 text-xs text-slate-500">
            {data.session.mode} · {data.scenario?.title} · {data.session.status}
            {data.session.metadata?.assignedPersona && <> · persona: {data.session.metadata.assignedPersona}</>}
          </div>
        </div>
        <Link href="/research/sessions" className="btn">← 목록</Link>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={`px-3 py-2 text-sm font-medium ${tab === t ? "border-b-2 border-emerald-600 text-emerald-700" : "text-slate-500 hover:text-slate-700"}`}>
            {t}
          </button>
        ))}
      </div>

      {tab === "replay" && (
        <div className="card max-h-[40rem] space-y-3 overflow-y-auto p-4">
          {data.turns.map((t: Turn) => (
            <div key={t.id}>
              <MessageBubble turn={t} />
              {(feedbackByTurn[t.id] ?? []).length > 0 && (
                <div className="ml-4 mt-1 space-y-1">
                  {feedbackByTurn[t.id].map((f: any) => (
                    <div key={f.id} className="inline-block rounded-md bg-violet-50 px-2 py-1 text-[11px] text-violet-700">
                      👆 {f.type} — {productById[f.productId]?.title ?? f.productId}
                      {f.reasonText && <> · &quot;{f.reasonText}&quot;</>}
                    </div>
                  ))}
                </div>
              )}
              {(correctionsByTurnIndex[t.turnIndex] ?? []).length > 0 && (
                <div className="ml-4 mt-1 space-y-1">
                  {correctionsByTurnIndex[t.turnIndex].map((c: any) => (
                    <div key={c.id} className="inline-block rounded-md bg-[#fff3e6] px-2 py-1 text-[11px] text-[#c2410c]">
                      ✏️ 칩 수정: {CORRECTION_LABEL[c.action] ?? c.action} — &quot;{c.before?.label}&quot;
                      {c.action === "edit_label" && c.manualLabel && <> → &quot;{c.manualLabel}&quot;</>}
                      {c.before?.priority !== c.after?.priority && <> ({c.before?.priority}→{c.after?.priority})</>}
                    </div>
                  ))}
                </div>
              )}
              {(markersByTurnIndex[t.turnIndex] ?? []).length > 0 && (
                <div className="ml-4 mt-1 flex flex-wrap gap-1">
                  {markersByTurnIndex[t.turnIndex].map((m: any) => (
                    <span key={m.id} className="inline-block rounded-md bg-[#eef2ff] px-2 py-1 text-[11px] text-[#4f46e5]">
                      {MARKER_LABEL[m.tag] ?? m.tag}{m.note ? `: ${m.note}` : ""}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "spec" && (
        <div className="card p-5">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-bold">참가자 자연어 명세 (AI memory)</h2>
            {spec && (
              <span className="rounded-full bg-[#eef2ff] px-2.5 py-1 text-[10px] font-medium text-[#4338ca]">
                v{spec.version} · 참가자 {data.session?.participantId}
              </span>
            )}
          </div>
          <p className="mb-3 text-xs text-[#9aa0a6]">
            대화가 이어질수록 보완되는 사용자 명세서 — KG의 사람용 렌더링입니다.
            수정은 칩에서 하고 이 파일은 그 결과를 비추는 거울입니다.
          </p>
          {spec?.specMarkdown ? (
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-[#e4e8eb] bg-[#fbfcfe] p-4 text-xs leading-relaxed text-[#404040]">
{spec.specMarkdown}
            </pre>
          ) : (
            <div className="text-sm text-[#b0b8c1]">아직 명세가 비어 있습니다 (대화를 진행하면 채워집니다).</div>
          )}
        </div>
      )}

      {tab === "trajectory" && (
        <div className="space-y-4">
          <div className="card p-4">
            <h2 className="mb-3 text-sm font-bold">Value Trajectory (이론모듈 §8)</h2>
            <ValueTrajectory snapshots={data.snapshots} />
          </div>
          {profile && (
            <div className="card p-4">
              <h2 className="text-sm font-bold">Continuous Value Profile (이론모듈 §12)</h2>
              <div className="mt-3 grid gap-4 md:grid-cols-3 text-xs">
                <div>
                  <div className="mb-1.5 font-semibold text-[#787c82]">Anchors</div>
                  {Object.entries(profile.anchors ?? {}).map(([k, v]: any) => (
                    <div key={k} className="mb-1 flex items-center gap-2">
                      <span className="w-20 text-[#606060]">{k}</span>
                      <div className="h-2 flex-1 rounded-full bg-[#f0f2f4]">
                        <div className="h-2 rounded-full bg-[#4f46e5]" style={{ width: `${Math.min(v * 100, 100)}%` }} />
                      </div>
                      <span className="w-8 font-mono">{Number(v).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-1.5 font-semibold text-[#787c82]">User Type Lens</div>
                  {Object.entries(profile.userTypes ?? {}).map(([k, v]: any) => (
                    <div key={k} className="mb-1 flex items-center gap-2">
                      <span className="w-32 text-[#606060]">{k}</span>
                      <div className="h-2 flex-1 rounded-full bg-[#f0f2f4]">
                        <div className="h-2 rounded-full bg-[#0073e6]" style={{ width: `${Math.min(v * 100, 100)}%` }} />
                      </div>
                      <span className="w-8 font-mono">{Number(v).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-1.5 font-semibold text-[#787c82]">Discovered Features</div>
                  {Object.keys(profile.discoveredFeatures ?? {}).length === 0 && (
                    <div className="text-[#b0b8c1]">이 세션과 연결된 발견 feature 없음</div>
                  )}
                  {Object.entries(profile.discoveredFeatures ?? {}).map(([k, v]: any) => (
                    <div key={k} className="mb-1 flex items-center gap-2">
                      <span className="flex-1 text-[#606060]">{k}</span>
                      <span className="font-mono">{Number(v).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "ontology" && (
        <div className="card p-4">
          <OntologyGraph topics={data.topics} relations={data.relations} />
        </div>
      )}

      {tab === "rig" && (
        <div className="space-y-4">
          {/* B. 메타경로 */}
          <div className="card p-4">
            <h2 className="text-sm font-bold">의도 구체화 경로 (메타경로)</h2>
            <p className="mt-1 text-xs text-[#9aa0a6]">대화 → 의도(이론) → … → 최종 상품. 의도가 어떻게 구체화됐는지의 흐름.</p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
              {(metaPath?.steps ?? []).map((s: any, i: number) => (
                <div key={i} className="flex items-center gap-1.5">
                  <div className="rounded-lg border border-[#e4e8eb] bg-white px-2 py-1.5">
                    <div className="text-[10px] text-[#9aa0a6]">t{s.turnIndex} · 대화</div>
                    <div className="max-w-[160px] truncate text-[#404040]">{s.utterance}</div>
                    {s.intentions.map((it: any, j: number) => (
                      <div key={j} className="mt-0.5 flex items-center gap-1">
                        <span className="rounded bg-[#eef2ff] px-1 py-0.5 text-[10px] text-[#4338ca]">{it.label.slice(0, 18)}</span>
                        {it.anchor && <span className="text-[9px] text-[#9aa0a6]">→ {it.anchor}</span>}
                      </div>
                    ))}
                  </div>
                  {i < (metaPath?.steps?.length ?? 0) - 1 && <span className="text-[#c9cdd2]">→</span>}
                </div>
              ))}
              {metaPath?.finalProduct && (
                <>
                  <span className="text-[#c9cdd2]">→</span>
                  <div className="rounded-lg border border-[#9fe7bf] bg-[#ecfdf5] px-2 py-1.5">
                    <div className="text-[10px] text-[#047857]">최종 상품</div>
                    <div className="max-w-[160px] truncate text-[#065f46]">{metaPath.finalProduct.title}</div>
                  </div>
                </>
              )}
              {(metaPath?.steps ?? []).length === 0 && <span className="text-[#b0b8c1]">경로 없음</span>}
            </div>
          </div>

          {/* C. 경로 기반 예측 */}
          <div className="card p-4">
            <h2 className="text-sm font-bold">경로 기반 예측 (RIG)</h2>
            <p className="mt-1 text-xs text-[#9aa0a6]">
              이 세션에서 나온 개념을 공유하는 다른 세션 {predict?.matchedSessions ?? 0}개로부터 예측 —
              데이터가 적어도 [의도-개념-이론] 공통 경로로 유사 사용자를 빌려옵니다.
            </p>
            <div className="mt-3 grid gap-4 md:grid-cols-2 text-xs">
              <div>
                <div className="mb-1 font-bold text-[#4338ca]">예측되는 다음 의도</div>
                {(predict?.predictedNextIntentions ?? []).length === 0 && <div className="text-[#b0b8c1]">예측 근거 부족</div>}
                {(predict?.predictedNextIntentions ?? []).map((p: any, i: number) => (
                  <div key={i} className="mb-1.5 rounded-lg bg-[#eef2ff] px-2.5 py-1.5">
                    <div className="font-medium text-[#3730a3]">{p.conceptLabel} <span className="text-[10px] text-[#9aa0a6]">(지지 {p.support})</span></div>
                    {p.exampleIntention && <div className="text-[10px] text-[#606060]">예: &quot;{p.exampleIntention}&quot;{p.topAnchor ? ` → ${p.topAnchor}` : ""}</div>}
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-1 font-bold text-[#047857]">예측되는 최종 상품</div>
                {(predict?.predictedFinalProducts ?? []).length === 0 && <div className="text-[#b0b8c1]">근거 부족</div>}
                {(predict?.predictedFinalProducts ?? []).map((p: any, i: number) => (
                  <div key={i} className="mb-1 rounded bg-[#ecfdf5] px-2 py-1 text-[#065f46]">
                    {p.title} <span className="text-[10px] text-[#9aa0a6]">(지지 {p.support})</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-2 text-[10px] text-[#9aa0a6]">
              지나온 개념: {(predict?.currentConcepts ?? []).join(" → ") || "–"}
            </div>
          </div>

          {/* A. 이론 단계 전이 (세션 횡단 집계) */}
          <div className="card p-4">
            <h2 className="text-sm font-bold">이론 단계 전이 <span className="font-normal text-[#9aa0a6]">(전체 {transitions?.sessionCount ?? 0}개 세션 집계)</span></h2>
            <p className="mt-1 text-xs text-[#9aa0a6]">대화가 진행되며 dominant 가치가 어떤 이론에서 어떤 이론으로 넘어가는지.</p>
            <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]">
              {(transitions?.transitions ?? []).length === 0 && <span className="text-[#b0b8c1]">전이 없음</span>}
              {(transitions?.transitions ?? []).slice(0, 12).map((t: any, i: number) => (
                <span key={i} className="rounded-full border border-[#e4e8eb] bg-white px-2.5 py-1">
                  <b className="text-[#4338ca]">{t.from}</b> → <b className="text-[#4338ca]">{t.to}</b>
                  <span className="ml-1 text-[10px] text-[#9aa0a6]">×{t.count}</span>
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "timeline" && (
        <div className="card p-4">
          <SnapshotTimeline snapshots={data.snapshots} />
        </div>
      )}

      {tab === "conflicts" && (
        <div className="space-y-3">
          {data.conflicts.length === 0 && <div className="card p-6 text-center text-sm text-slate-400">conflict 없음</div>}
          {data.conflicts.map((c: any) => (
            <div key={c.id} className="card p-4 text-sm">
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${c.severity === "direct" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"}`}>
                  {c.severity}
                </span>
                <span className="font-mono text-[10px] text-slate-400">{c.conflictType}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] ${c.status === "open" || c.status === "shown_to_user" ? "bg-sky-50 text-sky-600" : "bg-emerald-50 text-emerald-600"}`}>
                  {c.status}
                </span>
              </div>
              <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                <div><span className="text-slate-400">기존:</span> {c.oldAssumption}</div>
                <div><span className="text-slate-400">새 신호:</span> {c.newSignal}</div>
              </div>
              <p className="mt-2 text-xs text-slate-600">{c.explanationForResearcher}</p>
              {data.resolutions.filter((r: any) => r.conflictId === c.id).map((r: any) => (
                <div key={r.id} className="mt-2 rounded bg-emerald-50 px-2 py-1 text-[11px] text-emerald-700">
                  ✓ 해결: {r.action} {r.manualText && `— "${r.manualText}"`}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {tab === "pairs" && (
        <div className="space-y-3">
          {data.pairs.length === 0 && <div className="card p-6 text-center text-sm text-slate-400">pair 없음</div>}
          {data.pairs.map((p: any) => (
            <div key={p.id} className="card p-4 text-xs">
              <div className="flex items-center gap-2 text-[10px] text-slate-400">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{p.labelSource}</span>
                <span>{p.promptContext}</span>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 p-2">
                  <div className="text-[10px] font-bold text-emerald-600">CHOSEN</div>
                  {productById[p.chosenId]?.title ?? p.chosenId}
                </div>
                <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-2">
                  <div className="text-[10px] font-bold text-rose-600">REJECTED</div>
                  {productById[p.rejectedId]?.title ?? p.rejectedId}
                </div>
              </div>
              {p.userReasonText && <div className="mt-1.5 text-slate-600">사용자 이유: &quot;{p.userReasonText}&quot;</div>}
              <div className="mt-1 text-slate-500">{p.productDiff?.naturalLanguageSummary}</div>
              {p.inferredHiddenReason && (
                <div className="mt-1 rounded bg-indigo-50 px-2 py-1 text-indigo-700">
                  추론된 hidden reason: {p.inferredHiddenReason}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "evidence" && (
        <div className="card overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-100 bg-slate-50 text-slate-500">
              <tr>
                {["topic", "status", "priority", "confidence", "source", "anchors", "concepts", "evidence"].map((h) => (
                  <th key={h} className="px-3 py-2 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.topics.map((t: any) => (
                <tr key={t.id} className="border-b border-slate-50 align-top">
                  <td className="px-3 py-2 font-medium">{t.label}</td>
                  <td className="px-3 py-2">{t.status}</td>
                  <td className="px-3 py-2">{t.priority}</td>
                  <td className="px-3 py-2 font-mono">{t.confidence.toFixed(2)}</td>
                  <td className="px-3 py-2">{t.source}</td>
                  <td className="px-3 py-2">
                    {(t.anchorMappings ?? []).map((a: any) => `${a.anchor}(${a.score})`).join(", ")}
                  </td>
                  <td className="px-3 py-2">{(t.concepts ?? []).map((c: any) => c.label).join(", ")}</td>
                  <td className="px-3 py-2 text-slate-400">{t.evidenceIds.length}개</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "gap" && (
        <div className="space-y-4">
          <div className="card p-4">
            <h2 className="text-sm font-bold">Ground-truth Gap 분석 (DG5)</h2>
            <p className="mt-1 text-xs text-[#9aa0a6]">
              회상 인터뷰에서 추출한 hidden intention을 한 줄에 하나씩 입력하면, 시스템 KG가
              무엇을 잡았고(caught) 놓쳤고(missed) 새로 발견했는지(extra) 대조합니다.
            </p>
            <textarea
              value={gtText}
              onChange={(e) => setGtText(e.target.value)}
              rows={4}
              placeholder={"예)\n선물로 너무 저렴해 보이지 않기\n운동 친구의 생활양식에 맞기\n오래 써도 믿을 수 있음"}
              className="mt-2 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs focus:border-[#4f46e5] focus:outline-none"
            />
            <button onClick={saveGroundTruth} className="btn btn-primary mt-2 text-xs">저장 + 대조</button>
          </div>

          {gap && gap.groundTruthCount > 0 && (
            <div className="card p-4">
              <div className="mb-3 flex items-center gap-4 text-xs">
                <span>Recall <b className="font-mono text-[#4f46e5]">{gap.recall != null ? (gap.recall * 100).toFixed(0) + "%" : "–"}</b></span>
                <span className="text-[#9aa0a6]">caught {gap.caught.length} · missed {gap.missed.length} · 신규발견 {gap.discoveryCount}</span>
              </div>
              <div className="grid gap-3 md:grid-cols-3 text-xs">
                <div>
                  <div className="mb-1 font-bold text-[#047857]">✓ Caught</div>
                  {gap.caught.map((c: any, i: number) => (
                    <div key={i} className="mb-1 rounded bg-[#ecfdf5] px-2 py-1">
                      {c.groundTruth}<div className="text-[10px] text-[#9aa0a6]">→ {c.systemTopic}</div>
                    </div>
                  ))}
                </div>
                <div>
                  <div className="mb-1 font-bold text-[#e03131]">✗ Missed (시스템이 놓침)</div>
                  {gap.missed.length === 0 && <div className="text-[#b0b8c1]">없음</div>}
                  {gap.missed.map((m: string, i: number) => (
                    <div key={i} className="mb-1 rounded bg-[#fff5f5] px-2 py-1">{m}</div>
                  ))}
                </div>
                <div>
                  <div className="mb-1 font-bold text-[#8a6d00]">+ 신규 발견 (ground-truth 밖)</div>
                  {gap.extra.map((e: any, i: number) => (
                    <div key={i} className="mb-1 rounded bg-[#fffbe6] px-2 py-1">
                      {e.label}<span className="ml-1 text-[10px] text-[#9aa0a6]">[{e.source}/{e.explicitness}]</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
