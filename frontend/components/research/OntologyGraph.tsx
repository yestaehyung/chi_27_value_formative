"use client";

import { useMemo, useState } from "react";
import { Relation, Topic, ValueAnchor } from "@/lib/types";

// VAPT(arXiv:2601.22440) 스타일 방사형 value mirror:
// 7 value anchor를 바깥 고정점으로 두고, 각 hidden intention topic을 자신이 매핑된
// anchor 방향(매핑 강도 가중)으로 배치한다. anchor-topic 연결선 = value-grounding trail,
// topic-topic 곡선 = 관계(충돌=빨강). 노드를 클릭하면 근거/concept를 옆에 펼친다.

const ANCHORS: ValueAnchor[] = [
  "Functional", "Social", "Emotional", "Epistemic", "Conditional", "Hedonic", "Utilitarian",
];

const EDGE_COLOR: Record<string, string> = {
  CONFLICTS_WITH: "#e11d48",
  REVISES: "#f59e0b",
  WEAKENS: "#f43f5e",
  REFINES: "#8b5cf6",
  MOTIVATES: "#059669",
  SUPPORTS: "#10b981",
  PRIORITIZES: "#0ea5e9",
  RESOLVES: "#94a3b8",
};

// topic 상태/종류별 노드 색 (brand indigo 계열 + 의미색)
function topicStyle(t: Topic): { fill: string; stroke: string; dashed: boolean } {
  const kind = (t as any).hints?.kind;
  if (kind === "avoidance") return { fill: "#fff1f2", stroke: "#e11d48", dashed: false };
  if (t.status === "confirmed" || t.status === "corrected_by_user")
    return { fill: "#4f46e5", stroke: "#4338ca", dashed: false };
  if (t.status === "candidate") return { fill: "#eef2ff", stroke: "#a5b4fc", dashed: true };
  return { fill: "#e0e7ff", stroke: "#818cf8", dashed: false }; // inferred
}

export default function OntologyGraph({
  topics,
  relations,
}: {
  topics: Topic[];
  relations: Relation[];
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const active = useMemo(
    () => topics.filter((t) => !["rejected_by_user", "inactive"].includes(t.status)),
    [topics]
  );

  const W = 640;
  const H = 560;
  const cx = W / 2;
  const cy = H / 2;
  const rAnchor = 215;
  const rLabel = 250;

  // anchor 좌표
  const anchorPos = useMemo(() => {
    const m: Record<string, { x: number; y: number; ax: number; ay: number; lx: number; ly: number }> = {};
    ANCHORS.forEach((a, i) => {
      const ang = (Math.PI * 2 * i) / ANCHORS.length - Math.PI / 2;
      m[a] = {
        x: cx + Math.cos(ang) * rAnchor,
        y: cy + Math.sin(ang) * rAnchor,
        ax: Math.cos(ang),
        ay: Math.sin(ang),
        lx: cx + Math.cos(ang) * rLabel,
        ly: cy + Math.sin(ang) * rLabel,
      };
    });
    return m;
  }, [cx, cy]);

  // topic 좌표: 매핑된 anchor들의 강도 가중 방향. confidence 높을수록 anchor 쪽(바깥)으로.
  const topicPos = useMemo(() => {
    const placed: { id: string; x: number; y: number }[] = [];
    const m: Record<string, { x: number; y: number }> = {};
    for (const t of active) {
      let vx = 0, vy = 0, sum = 0;
      for (const a of t.anchorMappings ?? []) {
        const ap = anchorPos[a.anchor];
        if (!ap) continue;
        vx += ap.ax * a.score;
        vy += ap.ay * a.score;
        sum += a.score;
      }
      let ang: number;
      if (sum > 0.01) ang = Math.atan2(vy, vx);
      else ang = Math.random() * Math.PI * 2;
      const rT = rAnchor * (0.34 + 0.34 * Math.min(t.confidence ?? 0.5, 1));
      let x = cx + Math.cos(ang) * rT;
      let y = cy + Math.sin(ang) * rT;
      // 간단한 충돌 회피: 가까운 노드가 있으면 각도를 조금씩 돌림
      let tries = 0;
      while (tries < 18 && placed.some((p) => Math.hypot(p.x - x, p.y - y) < 56)) {
        ang += 0.4;
        const rr = rT + (tries % 2 ? 26 : -18);
        x = cx + Math.cos(ang) * rr;
        y = cy + Math.sin(ang) * rr;
        tries++;
      }
      placed.push({ id: t.id, x, y });
      m[t.id] = { x, y };
    }
    return m;
  }, [active, anchorPos, cx, cy]);

  const byId = useMemo(() => Object.fromEntries(active.map((t) => [t.id, t])), [active]);
  const sel = selected ? byId[selected] : null;

  const isDim = (id: string) =>
    selected != null &&
    id !== selected &&
    !relations.some(
      (r) =>
        (r.sourceTopicId === selected && r.targetTopicId === id) ||
        (r.targetTopicId === selected && r.sourceTopicId === id)
    );

  // 줌: viewBox를 중심 기준으로 확대/축소 (zoom>1 = 확대, <1 = 축소)
  const [zoom, setZoom] = useState(1);
  const vbW = W / zoom;
  const vbH = H / zoom;
  const vbX = (W - vbW) / 2;
  const vbY = (H - vbH) / 2;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-[#f8f9ff] to-[#f0f2f8]">
        {/* 줌 컨트롤 */}
        <div className="absolute right-2 top-2 z-10 flex flex-col overflow-hidden rounded-lg border border-[#e4e8eb] bg-white shadow-sm">
          <button
            onClick={(e) => { e.stopPropagation(); setZoom((z) => Math.min(z * 1.25, 3)); }}
            className="px-2.5 py-1 text-sm font-bold text-[#404040] hover:bg-[#f5f6f8]"
            aria-label="확대"
          >＋</button>
          <button
            onClick={(e) => { e.stopPropagation(); setZoom((z) => Math.max(z / 1.25, 0.5)); }}
            className="border-t border-[#f0f2f4] px-2.5 py-1 text-sm font-bold text-[#404040] hover:bg-[#f5f6f8]"
            aria-label="축소"
          >－</button>
          <button
            onClick={(e) => { e.stopPropagation(); setZoom(1); }}
            className="border-t border-[#f0f2f4] px-2.5 py-1 text-[10px] text-[#787c82] hover:bg-[#f5f6f8]"
            aria-label="원래대로"
          >리셋</button>
        </div>
        <svg
          viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
          className="block max-h-[calc(100vh-15rem)] w-full"
          onClick={() => setSelected(null)}
        >
          {/* 가이드 링 */}
          {[0.55, 0.8, 1].map((g) => (
            <circle key={g} cx={cx} cy={cy} r={rAnchor * g} fill="none" stroke="#e4e8ef" strokeWidth={1} />
          ))}

          {/* value-grounding trails: topic → 매핑 anchor */}
          {active.flatMap((t) =>
            (t.anchorMappings ?? []).map((a) => {
              const tp = topicPos[t.id];
              const ap = anchorPos[a.anchor];
              if (!tp || !ap) return null;
              return (
                <line
                  key={`${t.id}-${a.anchor}`}
                  x1={tp.x} y1={tp.y} x2={ap.x} y2={ap.y}
                  stroke="#4f46e5"
                  strokeWidth={Math.max(a.score * 2.4, 0.5)}
                  opacity={isDim(t.id) ? 0.04 : 0.18 + a.score * 0.22}
                />
              );
            })
          )}

          {/* topic ↔ topic 관계 곡선 */}
          {relations.map((r) => {
            const s = topicPos[r.sourceTopicId];
            const e = topicPos[r.targetTopicId];
            if (!s || !e) return null;
            const color = EDGE_COLOR[r.type] ?? "#94a3b8";
            const mx = (s.x + e.x) / 2 + (e.y - s.y) * 0.18;
            const my = (s.y + e.y) / 2 - (e.x - s.x) * 0.18;
            const dim = selected != null && r.sourceTopicId !== selected && r.targetTopicId !== selected;
            return (
              <path
                key={r.id}
                d={`M ${s.x} ${s.y} Q ${mx} ${my} ${e.x} ${e.y}`}
                fill="none" stroke={color}
                strokeWidth={r.type === "CONFLICTS_WITH" ? 2.2 : 1.4}
                strokeDasharray={r.type === "CONFLICTS_WITH" ? undefined : "4 3"}
                opacity={dim ? 0.06 : 0.7}
              />
            );
          })}

          {/* 이론 간 대립: Hedonic ↔ Utilitarian (쇼핑가치 양극) */}
          {anchorPos["Hedonic"] && anchorPos["Utilitarian"] && (
            <g>
              <line
                x1={anchorPos["Hedonic"].x} y1={anchorPos["Hedonic"].y}
                x2={anchorPos["Utilitarian"].x} y2={anchorPos["Utilitarian"].y}
                stroke="#94a3b8" strokeWidth={1.4} strokeDasharray="2 4" opacity={0.55}
              />
              <text
                x={(anchorPos["Hedonic"].x + anchorPos["Utilitarian"].x) / 2}
                y={(anchorPos["Hedonic"].y + anchorPos["Utilitarian"].y) / 2 - 3}
                textAnchor="middle" fontSize={8} fill="#94a3b8"
              >
                대립
              </text>
            </g>
          )}

          {/* anchor 노드 (바깥 고정점) */}
          {ANCHORS.map((a) => {
            const ap = anchorPos[a];
            return (
              <g key={a}>
                <circle cx={ap.x} cy={ap.y} r={7} fill="#fff" stroke="#c7cdf5" strokeWidth={2} />
                <circle cx={ap.x} cy={ap.y} r={3} fill="#6366f1" />
                <text
                  x={ap.lx} y={ap.ly}
                  textAnchor={ap.ax > 0.3 ? "start" : ap.ax < -0.3 ? "end" : "middle"}
                  dominantBaseline="middle"
                  fontSize={11} fontWeight={700} fill="#4338ca"
                  stroke="#ffffff" strokeWidth={3.5} strokeLinejoin="round"
                  style={{ paintOrder: "stroke" }}
                >
                  {a}
                </text>
              </g>
            );
          })}

          {/* topic 노드 */}
          {active.map((t) => {
            const tp = topicPos[t.id];
            if (!tp) return null;
            const st = topicStyle(t);
            const dim = isDim(t.id);
            const rad = 7 + Math.min((t.evidenceIds?.length ?? 1), 4) * 1.6;
            const isSel = selected === t.id;
            const label = t.label.length > 16 ? t.label.slice(0, 16) + "…" : t.label;
            return (
              <g
                key={t.id}
                className="cursor-pointer"
                opacity={dim ? 0.25 : 1}
                onClick={(e) => { e.stopPropagation(); setSelected(isSel ? null : t.id); }}
              >
                <circle
                  cx={tp.x} cy={tp.y} r={isSel ? rad + 3 : rad}
                  fill={st.fill} stroke={st.stroke}
                  strokeWidth={isSel ? 3 : 1.5}
                  strokeDasharray={st.dashed ? "3 2" : undefined}
                />
                <text
                  x={tp.x} y={tp.y - rad - 4}
                  textAnchor="middle" fontSize={9.5}
                  fill="#1e1b4b" fontWeight={isSel ? 700 : 500}
                  stroke="#ffffff" strokeWidth={3.2} strokeLinejoin="round"
                  style={{ paintOrder: "stroke" }}
                >
                  {label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* 사이드: 범례 + 선택 상세 */}
      <div className="space-y-3 text-xs">
        <div className="card p-3">
            <div className="mb-2 font-bold text-[#191919]">읽는 법</div>
            <div className="space-y-1.5 text-[11px] text-[#606060]">
              <div>· 바깥 7개 점 = 가치 anchor (TCV 5 + Hedonic/Utilitarian)</div>
              <div>· 가운데 노드 = hidden intention topic. anchor 쪽으로 끌릴수록 그 가치가 강함</div>
              <div>· 가는 선 = 가치 근거(evidence) trail, 굵을수록 강한 매핑</div>
              <div className="flex items-center gap-1.5"><span className="inline-block h-2 w-4" style={{ background: "#e11d48" }} /> 빨강 곡선 = 가치 충돌</div>
              <div>· 의도 간 곡선 = 관계 (인과 MOTIVATES·REFINES / 동시 CONFLICTS·SUPPORTS / 시간 REVISES·WEAKENS)</div>
              <div className="flex items-center gap-1.5"><span className="inline-block h-px w-4 border-t border-dashed border-[#94a3b8]" /> 점선 = Hedonic↔Utilitarian 대립축</div>
              <div className="mt-2 flex flex-wrap gap-1">
                <span className="rounded px-1.5 py-0.5" style={{ background: "#4f46e5", color: "#fff" }}>확정</span>
                <span className="rounded px-1.5 py-0.5" style={{ background: "#e0e7ff", color: "#3730a3" }}>추론</span>
                <span className="rounded border border-dashed px-1.5 py-0.5" style={{ borderColor: "#a5b4fc", color: "#6366f1" }}>후보</span>
                <span className="rounded px-1.5 py-0.5" style={{ background: "#fff1f2", color: "#e11d48" }}>회피</span>
              </div>
              <div className="mt-2 text-[#9aa0a6]">노드를 클릭하면 아래에 근거가 나타나요.</div>
            </div>
          </div>
        {sel && (
          <div className="card p-3">
            <div className="text-sm font-bold text-[#191919]">{sel.label}</div>
            <div className="mt-0.5 flex flex-wrap gap-1 text-[10px]">
              <span className="rounded bg-[#f0f2f8] px-1.5 py-0.5">{sel.status}</span>
              <span className="rounded bg-[#f0f2f8] px-1.5 py-0.5">{sel.priority}</span>
              <span className="rounded bg-[#f0f2f8] px-1.5 py-0.5">conf {sel.confidence?.toFixed(2)}</span>
            </div>
            {sel.description && <p className="mt-2 text-[11px] text-[#606060]">{sel.description}</p>}

            {(sel.anchorMappings ?? []).length > 0 && (
              <div className="mt-2">
                <div className="mb-1 text-[10px] font-bold text-[#9aa0a6]">VALUE ANCHORS</div>
                {(sel.anchorMappings ?? []).slice().sort((a, b) => b.score - a.score).map((a) => (
                  <div key={a.id} className="mb-1 flex items-center gap-1.5">
                    <span className="w-20 text-[11px] text-[#404040]">{a.anchor}</span>
                    <div className="h-1.5 flex-1 rounded-full bg-[#eef2ff]">
                      <div className="h-1.5 rounded-full bg-[#4f46e5]" style={{ width: `${a.score * 100}%` }} />
                    </div>
                    <span className="font-mono text-[10px] text-[#9aa0a6]">{a.score.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}

            {(sel.concepts ?? []).length > 0 && (
              <div className="mt-2">
                <div className="mb-1 text-[10px] font-bold text-[#9aa0a6]">CONCEPTS</div>
                <div className="flex flex-wrap gap-1">
                  {(sel.concepts ?? []).map((c) => (
                    <span key={c.id} className="rounded-full bg-[#ecfdf5] px-2 py-0.5 text-[10px] text-[#047857]">{c.label}</span>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-2 text-[10px] text-[#9aa0a6]">
              근거 {sel.evidenceIds?.length ?? 0}개 · source: {sel.source}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
