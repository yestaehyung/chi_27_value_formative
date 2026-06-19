"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import AnchorRadar from "@/components/preference/AnchorRadar";
import MotivationRadar from "@/components/preference/MotivationRadar";

const INTENT_GLOSS: Record<string, string> = {
  Reveal: "새 요구를 드러냄", Interpret: "답변·구체화", Revise: "이전 선호 수정", Inquire: "되물음", Chitchat: "잡담",
};
const ACTION_GLOSS: Record<string, string> = {
  Clarify: "되물어 명확히", Recommend: "상품 추천", "No answer": "답변 못함", Inquire: "질문", Interpret: "해석", Chitchat: "잡담",
};

const cleanTitle = (s?: string) => (s || "").replace(/\((liked|disliked)\)/gi, "").trim();
const STEP_MS = 1100; // 턴당 재생 간격

function ActTag({ value, tone }: { value: string; tone: "intent" | "action" }) {
  const c = tone === "intent" ? "bg-[#eef2ff] text-[#4338ca]" : "bg-[#eff8ff] text-[#0369a1]";
  const gloss = (tone === "intent" ? INTENT_GLOSS : ACTION_GLOSS)[value];
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${c}`} title={gloss}>{value}</span>
  );
}

export default function PsconViewerPage() {
  const { convId } = useParams<{ convId: string }>();
  const [data, setData] = useState<any>(null);
  const [timeline, setTimeline] = useState<any>(null);
  const [evidence, setEvidence] = useState<any>(null);
  const [hlAnchor, setHlAnchor] = useState<string | null>(null);
  const [shown, setShown] = useState<number>(-1); // -1 = 전체 표시(기본), ≥0 = 재생 중 노출 턴 수
  const [playing, setPlaying] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!convId) return;
    api.psconConversation(convId).then(setData).catch(console.error);
    api.psconTimeline(convId).then(setTimeline).catch(() => setTimeline(null));
    api.psconEvidence(convId).then(setEvidence).catch(() => setEvidence(null));
  }, [convId]);

  const turns: any[] = data?.conversation || [];
  const total = turns.length;
  const visible = shown < 0 ? total : Math.min(shown, total);
  const isComplete = visible >= total;

  // 자동 재생 — 한 턴씩 등장
  useEffect(() => {
    if (!playing) return;
    if (visible >= total) { setPlaying(false); return; }
    const id = setTimeout(() => setShown(visible + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [playing, visible, total]);

  // 등장할 때마다 맨 아래로 스크롤 (재생 중에만)
  useEffect(() => {
    const el = chatRef.current;
    if (el && shown >= 0) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [visible, shown]);

  if (!data) return <div className="py-20 text-center text-sm text-slate-400">불러오는 중…</div>;
  const ratingMap: Record<string, string> = data.ratingMap || {};
  const analysis = data.analysis; // 배치로 미리 계산된 결과 (없으면 null)

  // B: 재생 위치(노출된 user 턴 수)에 맞는 턴별 스냅샷 — DB에 이미 있는 시퀀스
  const steps: any[] = timeline?.steps || [];
  const userTurnsShown = turns.slice(0, visible).filter((t) => t.role === "user").length;
  const liveStep = steps.length ? steps[Math.min(Math.max(userTurnsShown - 1, 0), steps.length - 1)] : null;
  const live = !isComplete && !!liveStep;            // 재생 중 + 스냅샷 있음 → 실시간 방사형
  const playbackNoData = !isComplete && !liveStep;   // 재생 중인데 시퀀스 없음 → placeholder
  const radarScores = live ? liveStep.anchorScores : analysis?.anchorScores;
  const radarBreakdown = live ? liveStep.anchorBreakdown : analysis?.anchorBreakdown;
  const radarTopics = live ? liveStep.topics : analysis?.topics;
  // 동기 7축 (M8) — trait 5축과 층이 달라 별도 radar로 그린다 (한 다각형에 섞지 않음)
  const motivationScores = live ? liveStep.motivationScores : analysis?.motivationScores;

  // 가치 축 클릭 → 그 축을 근거한 대화 발화 하이라이트
  const hlTurns = new Set<number>(hlAnchor ? (evidence?.byAnchor?.[hlAnchor] || evidence?.byMotivation?.[hlAnchor] || []) : []);
  const hlOn = hlAnchor != null;
  const dimCls = (i: number) => (hlOn && hlTurns.size > 0 && !hlTurns.has(i) ? "opacity-30" : "");
  const isHit = (i: number) => hlOn && hlTurns.has(i); // 이 발화가 선택한 축의 근거인가

  const play = () => { if (visible >= total) setShown(1); setPlaying(true); };
  const pause = () => setPlaying(false);
  const showAll = () => { setShown(total); setPlaying(false); };

  // 다음에 등장할 턴이 시스템이면 타이핑 인디케이터 표시 (에이전트가 '생각 중')
  const nextIsSystem = playing && visible < total && turns[visible]?.role !== "user";

  return (
    <div className="space-y-3">
      {/* slim header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">
            PSCon 대화 <span className="font-mono text-sm font-normal text-slate-400">#{data.convId}</span>
          </h1>
          <div className="mt-0.5 text-xs text-slate-500">{total}턴 · 실제 쇼핑 대화 (읽기 전용)</div>
        </div>
        <Link href="/pscon" className="btn">← 목록</Link>
      </div>

      {/* 좌 대화 / 우 분석(방사형) — 스터디 세션과 동일 레이아웃 */}
      <div className="grid h-[calc(100vh-10rem)] grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_440px]">
        {/* LEFT: 대화 (+ 재생 컨트롤) */}
        <div className="card flex min-h-0 flex-col">
          <div className="flex items-center justify-between border-b border-[#f0f2f4] px-5 py-3">
            <div className="text-sm font-bold text-[#191919]">
              쇼핑 대화 <span className="ml-1 text-xs font-normal text-[#9aa0a6]">— PSCon 원본</span>
            </div>
            <div className="flex items-center gap-1.5 text-[11px]">
              {!isComplete && <span className="mr-1 font-mono text-[#9aa0a6]">{visible}/{total}</span>}
              {playing ? (
                <button onClick={pause} className="btn px-2.5 py-1 text-[11px]">⏸ 일시정지</button>
              ) : (
                <button onClick={play} className="btn btn-primary px-2.5 py-1 text-[11px]">
                  {isComplete ? "↻ 다시 재생" : "▶ 이어 재생"}
                </button>
              )}
              {!isComplete && <button onClick={showAll} className="btn px-2.5 py-1 text-[11px]">⏭ 전체</button>}
              {isComplete && !playing && <span className="ml-1 text-[#9aa0a6]">{total}턴</span>}
            </div>
          </div>
          {hlAnchor && (
            <div className="flex items-center justify-between border-b border-amber-200 bg-amber-50 px-5 py-1.5 text-[11px] text-amber-900">
              <span>🖍 <b>{hlAnchor}</b> 근거 발화 {hlTurns.size}개 하이라이트 {hlTurns.size === 0 && "(이 대화엔 없음)"}</span>
              <button onClick={() => setHlAnchor(null)} className="font-medium underline">해제</button>
            </div>
          )}
          <div ref={chatRef} className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
            {turns.slice(0, visible).map((t, i) => {
              if (t.role === "user") {
                const kw: string[] = t.keywords || [];
                return (
                  <div key={i} className={`msg-in flex justify-end transition-opacity ${dimCls(i)}`}>
                    <div className="max-w-[80%]">
                      <div className="mb-1 flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-[11px] text-[#9aa0a6]">
                        {kw.length > 0 && (
                          <span className="text-[10px] text-[#787c82]">
                            <span className="text-[#b0b8c1]">키워드</span> {kw.join(" · ")}
                          </span>
                        )}
                        {t.intent && <ActTag value={t.intent} tone="intent" />}
                        <span>사용자</span>
                      </div>
                      <div className={`whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed ${isHit(i) ? "bg-amber-200 text-[#191919] ring-1 ring-amber-400" : "bg-[#4f46e5] text-white"}`}>
                        {t.content}
                      </div>
                    </div>
                  </div>
                );
              }

              const rec: any[] = t.recommended_products || [];
              const clar: string[] = Array.isArray(t.clarifying_attribute) ? t.clarifying_attribute : [];
              return (
                <div key={i} className={`msg-in flex gap-2.5 transition-opacity ${dimCls(i)}`}>
                  <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#f0f2f4] text-[11px] font-bold text-[#787c82]">S</span>
                  <div className="min-w-0 max-w-[85%]">
                    <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-[#9aa0a6]">
                      <span className="font-medium text-[#404040]">시스템</span>
                      {t.action && <ActTag value={t.action} tone="action" />}
                    </div>
                    {t.content && (
                      <div className="whitespace-pre-wrap rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-2.5 text-sm leading-relaxed text-[#191919]">
                        {t.content}
                      </div>
                    )}
                    {clar.length > 0 && (
                      <div className="mt-1.5">
                        <div className="mb-1 text-[10px] text-[#9aa0a6]">제시한 선택지</div>
                        <div className="flex flex-wrap gap-1">
                          {clar.map((a, j) => (
                            <span key={j} className="rounded-full border border-[#dbe6f5] bg-[#f7fbff] px-2 py-0.5 text-[10px] text-[#0369a1]">{a}</span>
                          ))}
                        </div>
                      </div>
                    )}
                    {rec.length > 0 && (
                      <div className="mt-2">
                        <div className="mb-1 text-[10px] text-[#9aa0a6]">추천 상품</div>
                        <div className="grid gap-1.5">
                          {rec.map((p, j) => {
                            const r = ratingMap[p.product_id];
                            return (
                              <div
                                key={j}
                                className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 text-xs ${
                                  r === "liked"
                                    ? "border-emerald-200 bg-emerald-50/60"
                                    : r === "disliked"
                                      ? "border-rose-200 bg-rose-50/60"
                                      : "border-[#e4e8eb] bg-white"
                                }`}
                              >
                                {r && (
                                  <span className={`shrink-0 rounded px-1 text-[10px] font-semibold ${r === "liked" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                                    {r === "liked" ? "좋아요" : "싫어요"}
                                  </span>
                                )}
                                <span className="min-w-0 leading-snug text-[#404040]">{cleanTitle(p.product_rate) || p.product_id}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* 시스템 턴 등장 직전 — 타이핑 인디케이터 */}
            {nextIsSystem && (
              <div className="msg-in flex gap-2.5">
                <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#f0f2f4] text-[11px] font-bold text-[#787c82]">S</span>
                <span className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-[#e4e8eb] bg-white px-4 py-3">
                  <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
                </span>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT: 우리 파이프라인 분석(방사형 + 추출 기준) + 읽는 법 */}
        <div className="min-h-0 space-y-3 overflow-y-auto pb-4 pr-1">
          <div className="card p-4">
            <div className="text-sm font-bold text-[#191919]">
              이 대화에서 추출한 hidden intention
            </div>
            {!analysis?.anchorScores ? (
              <div className="mt-2 text-xs leading-relaxed text-[#9aa0a6]">
                아직 분석되지 않은 대화예요. 배치 분석(<span className="font-mono">scripts/analyze_pscon.py</span>)이
                이 대화까지 처리하면 여기에 방사형 그래프와 추출된 기준이 나타납니다.
              </div>
            ) : playbackNoData ? (
              <div className="mt-3 border-t border-[#f0f2f4] pt-8 pb-8 text-center">
                <div className="text-sm font-semibold text-[#4f46e5]">▶ 재생 중…</div>
                <div className="mt-1.5 text-xs leading-relaxed text-[#9aa0a6]">
                  대화가 끝나면 여기에 추출된<br />방사형 그래프와 기준이 공개돼요.
                </div>
              </div>
            ) : (
              <div className="mt-3 border-t border-[#f0f2f4] pt-3">
                <div className="mb-1 text-center text-[11px] font-medium text-[#9aa0a6]">
                  가치 Anchor 분포
                  {live && <span className="ml-1 font-semibold text-[#4f46e5]">· ▶ 실시간 (user turn {userTurnsShown})</span>}
                </div>
                <div className="flex justify-center">
                  <AnchorRadar scores={radarScores} breakdown={radarBreakdown} size={260} onSelect={(a) => setHlAnchor(a)} />
                </div>
                {motivationScores && Object.keys(motivationScores).length > 0 && (
                  <>
                    <div className="mb-1 mt-4 text-center text-[11px] font-medium text-[#9aa0a6]">
                      쇼핑 동기 분포 <span className="font-normal">(상황적 — 세션 한정)</span>
                    </div>
                    <div className="flex justify-center">
                      <MotivationRadar scores={motivationScores} size={260} onSelect={(d) => setHlAnchor(d)} />
                    </div>
                  </>
                )}
                <div className="mb-1.5 mt-4 text-[11px] font-bold text-[#9aa0a6]">추출된 기준 · {radarTopics?.length ?? 0}개</div>
                <div className="space-y-1">
                  {(radarTopics ?? []).map((t: any, i: number) => (
                    <div key={i} className="rounded-lg border border-[#eef0f2] bg-white px-2.5 py-1.5 text-xs">
                      <span className="font-medium text-[#191919]">{t.label}</span>
                      <span className="ml-1.5 text-[10px] text-[#9aa0a6]">{t.explicitness} · {t.priority}</span>
                    </div>
                  ))}
                  {(radarTopics ?? []).length === 0 && (
                    <div className="text-xs text-[#b0b8c1]">{live ? "아직 추출된 기준이 없어요." : "추출된 기준이 없어요."}</div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* 읽는 법 — 좌측 대화의 칩 설명 */}
          <div className="card space-y-1.5 p-3 text-[11px] leading-relaxed text-[#787c82]">
            <div className="font-bold text-[#404040]">읽는 법 <span className="font-normal text-[#9aa0a6]">— 칩은 PSCon 원본 주석</span></div>
            <div>
              <span className="mr-1 rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-semibold text-[#4338ca]">의도</span>
              사용자 act — <b>Reveal</b> 새 요구 · <b>Interpret</b> 답변·구체화 · <b>Revise</b> 수정 · <b>Inquire</b> 되물음
            </div>
            <div>
              <span className="mr-1 rounded bg-[#eff8ff] px-1.5 py-0.5 text-[10px] font-semibold text-[#0369a1]">행동</span>
              시스템 act — <b>Clarify</b> 되묻기 · <b>Recommend</b> 추천 · <b>No answer</b> 등
            </div>
            <div>
              <b>키워드</b> 발화 핵심어 · <b>선택지</b> 시스템이 되물은 옵션 · <b className="text-[#047857]">좋아요</b>/<b className="text-[#e03131]">싫어요</b> 최종 평가
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
