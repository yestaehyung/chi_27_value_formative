"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Turn } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import AnchorRadar from "@/components/preference/AnchorRadar";
import MotivationRadar from "@/components/preference/MotivationRadar";

// 합성(LLM user agent) 대화 검수 — 목록 + 상세 마스터-디테일 (시뮬레이션 페이지에 임베드).
// 자동 판정(✅/❌)은 표시하지 않는다 — 주입 GT와 복원 결과를 나란히 보여주고
// 판단은 검수자가 한다 (평가는 사람·LLM의 별도 단계).
// GT v2는 persona×scenario 조건부라, 세션 토글을 바꾸면 GT 패널도 그 상황의 GT로 바뀐다.

const avatarUrl = (seed: string) =>
  `https://api.dicebear.com/9.x/notionists/svg?seed=${encodeURIComponent(seed)}`;

const FB: Record<string, string> = {
  like: "👍 좋아요", dislike: "👎 싫어요", view_detail: "🔍 자세히", purchase: "🛍 구매",
};
const VALUE_CLS: Record<string, string> = {
  dominant: "bg-[#4f46e5] text-white",
  present: "bg-[#eef2ff] text-[#4338ca]",
  trace: "bg-[#f1f3f5] text-[#9aa0a6]",
};
const MOT_CLS: Record<string, string> = {
  high: "bg-[#4f46e5] text-white",
  medium: "bg-[#eef2ff] text-[#4338ca]",
  low: "bg-[#f1f3f5] text-[#9aa0a6]",
};
const KIND_CLS: Record<string, string> = {
  constraint: "bg-[#fff5f5] text-[#e03131]",
  avoidance: "bg-[#fffbe6] text-[#8a6d00]",
  preference: "bg-[#eef2ff] text-[#4338ca]",
  context: "bg-[#f1f3f5] text-[#868b94]",
};
const EXP_KO: Record<string, string> = { explicit: "명시", implicit: "암시", latent: "잠재" };

// 직접 실행 탭과 동일한 페르소나 상세 모달용 — 10개 삶의 단면
const FACETS: [string, string, string][] = [
  ["professional_persona", "💼", "직업"],
  ["career_goals_and_ambitions", "🎯", "목표·포부"],
  ["skills_and_expertise", "🧩", "역량·전문성"],
  ["hobbies_and_interests", "🎨", "취미·관심"],
  ["culinary_persona", "🍽", "음식"],
  ["travel_persona", "✈️", "여행"],
  ["sports_persona", "🏃", "운동"],
  ["arts_persona", "🎭", "문화·여가"],
  ["family_persona", "👪", "가족"],
  ["cultural_background", "🌱", "가치관·배경"],
];

export default function SynthesisReview() {
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [sessIdx, setSessIdx] = useState(0);
  const [personas, setPersonas] = useState<any[]>([]);
  const [modalId, setModalId] = useState<string | null>(null);

  useEffect(() => {
    api.synthesisRuns().then(setData).catch(console.error);
    api.personas().then((d) => setPersonas(d.personas ?? [])).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    setDetail(null);
    setSessIdx(0);
    api.synthesisRun(selected).then(setDetail).catch(console.error);
  }, [selected]);

  if (!data) return <div className="py-20 text-center text-sm text-slate-400">불러오는 중…</div>;

  const runs: any[] = data.runs ?? [];

  // 페르소나 전체(10개 단면) 모달 — 목록·상세 양쪽에서 재사용 (별도 컴포넌트 없이 공유).
  // position:fixed라 트리 어디에 렌더해도 동일하게 뜬다.
  const personaModal = modalId && (() => {
    const p = personas.find((x: any) => x.id === modalId);
    const r = runs.find((x: any) => x.personaId === modalId);
    const pd = p?.demographics ?? {};
    const pnar = p?.narratives ?? {};
    const name = p?.name ?? r?.name ?? modalId;
    const chips = (p
      ? [
          [pd.province, pd.district].filter(Boolean).join(" · "),
          pd.education_level, pd.marital_status, pd.family_type, pd.housing_type, pd.bachelors_field,
        ]
      : []
    ).filter(Boolean) as string[];
    const facets = FACETS.filter(([k]) => pnar[k]);
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
           onClick={() => setModalId(null)}>
        <div className="flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
             onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between border-b border-[#e4e8eb] px-5 py-3">
            <h3 className="text-sm font-semibold">페르소나 상세</h3>
            <button onClick={() => setModalId(null)}
                    className="text-lg leading-none text-[#9aa0a6] hover:text-[#191919]">✕</button>
          </div>

          <div className="grid flex-1 grid-cols-1 overflow-hidden sm:grid-cols-[230px_1fr]">
            {/* 왼쪽 — 정체성 + 합성 액션 */}
            <div className="flex flex-col gap-3 border-b border-[#e4e8eb] p-5 sm:border-b-0 sm:border-r">
              <img src={avatarUrl(modalId)} alt="" className="h-24 w-24 rounded-2xl bg-[#eef2ff]" />
              <div>
                <div className="text-lg font-bold text-[#191919]">{name}</div>
                <div className="text-sm text-[#606060]">
                  {[pd.age && `${pd.age}세`, pd.sex, pd.occupation].filter(Boolean).join(" · ")}
                </div>
              </div>
              {chips.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {chips.map((c, i) => (
                    <span key={i} className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[11px] text-[#606060]">{c}</span>
                  ))}
                </div>
              )}
              {p?.personaNarrative && (
                <p className="text-xs leading-relaxed text-[#868b94]">{p.personaNarrative}</p>
              )}
              {r && (
                <div className="rounded-lg border border-[#eef0f2] bg-[#fbfcfe] p-2.5 text-[11px]">
                  <div className="truncate text-[#9aa0a6]">
                    🛒 {(r.scenarioTitles ?? [r.scenarioTitle ?? r.scenarioId]).filter(Boolean).join(" → ")}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <span className="text-[#9aa0a6]">주입 GT</span>
                    {(r.injected?.valueDominant ?? []).length === 0 && <span className="text-[#c8ccd0]">–</span>}
                    {(r.injected?.valueDominant ?? []).map((a: string) => (
                      <span key={a} className="rounded bg-[#4f46e5] px-1.5 py-0.5 font-medium text-white">{a}</span>
                    ))}
                    {(r.injected?.motivationHigh ?? []).map((a: string) => (
                      <span key={a} className="rounded bg-[#eef2ff] px-1.5 py-0.5 font-medium text-[#4338ca]">{a}</span>
                    ))}
                  </div>
                </div>
              )}
              <button
                onClick={() => { if (selected !== modalId) setSelected(modalId); setModalId(null); }}
                className="btn btn-primary mt-auto w-full"
              >
                {selected === modalId ? "이 대화로 돌아가기" : "🧪 합성 대화 확인 →"}
              </button>
            </div>

            {/* 오른쪽 — 10 내러티브 */}
            <div className="grid content-start gap-x-6 gap-y-3.5 overflow-y-auto p-5 md:grid-cols-2">
              {facets.length === 0 && (
                <p className="text-xs text-[#b0b8c1]">이 페르소나의 상세 서사가 없어요.</p>
              )}
              {facets.map(([k, icon, label]) => (
                <div key={k}>
                  <div className="text-xs font-semibold text-[#404040]">{icon} {label}</div>
                  <p className="mt-0.5 text-xs leading-relaxed text-[#606060]">{pnar[k]}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  })();

  // ── 상세 ──────────────────────────────────────────────
  if (selected) {
    if (!detail) return <div className="py-20 text-center text-sm text-slate-400">불러오는 중…</div>;
    const d = detail;
    const sessions: any[] = d.sessions ?? [];
    const sess = sessions[Math.min(sessIdx, Math.max(sessions.length - 1, 0))] ?? null;
    const gt = sess?.gt ?? d.gt ?? {};
    const rec = sess?.recovered ?? {};
    const inj = sess?.injected ?? {};
    const cross = d.crossSession;
    return (
      <div className="space-y-4">
        {/* 헤더 */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <img src={avatarUrl(d.personaId)} alt="" className="h-12 w-12 rounded-full bg-[#eef2ff]" />
            <div>
              <h2 className="text-lg font-bold text-[#191919]">{d.name}</h2>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>🛒 {sess?.scenarioTitle ?? d.scenario?.title}</span>
                {sess && (
                  <span className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[10px]">
                    {sess.ended === "purchase" ? `🛍 구매: ${sess.purchasedTitle ?? ""}` : "탐색 종료"}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button onClick={() => setModalId(d.personaId)} className="text-xs text-[#4338ca] hover:underline">
              페르소나 전체 보기
            </button>
            {sess?.sessionId && (
              <a href={`/research/session/${sess.sessionId}`} className="text-xs text-emerald-600 hover:underline">
                연구자 뷰 →
              </a>
            )}
            <button onClick={() => setSelected(null)} className="btn">← 합성 목록</button>
          </div>
        </div>

        {!d.synthesized ? (
          <div className="card p-8 text-center text-sm text-[#9aa0a6]">
            아직 이 페르소나는 합성되지 않았어요 (배치 진행 중일 수 있어요).
          </div>
        ) : (
          <>
            {/* 세션 토글 — persona당 세션이 2개 이상일 때만 */}
            {sessions.length > 1 && (
              <div className="flex flex-wrap gap-1.5">
                {sessions.map((s: any, i: number) => (
                  <button
                    key={s.sessionId}
                    onClick={() => setSessIdx(i)}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      i === sessIdx
                        ? "bg-[#4f46e5] text-white"
                        : "bg-[#f1f3f5] text-[#606060] hover:bg-[#eef2ff] hover:text-[#4338ca]"
                    }`}
                  >
                    세션 {i + 1} · {s.scenarioTitle}{s.multi ? " 🔗" : ""}
                  </button>
                ))}
              </div>
            )}

            {/* 상단 — 주입 GT (현재 세션 기준, 판정 없음) */}
            <div className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-bold text-[#191919]">
                  주입한 숨은 의도 (GT){sessions.length > 1 ? ` — 세션 ${sessIdx + 1}` : ""}
                </h3>
                <div className="flex shrink-0 items-center gap-1">
                  <span className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[10px] font-medium text-[#868b94]">
                    {gt.gtVersion === "v2" ? "v2 · 상황 조건부" : "v1 · persona 고정"}
                  </span>
                  <span className="rounded-full bg-[#fff5f5] px-2 py-0.5 text-[10px] font-medium text-[#e03131]">
                    쇼핑 에이전트엔 비공개
                  </span>
                </div>
              </div>
              {gt.gtVersion === "v2" && sessions.length > 1 && (
                <p className="mt-1 text-[10px] text-[#9aa0a6]">
                  현재 세션의 상황({sess?.scenarioTitle})에 대해 도출된 GT — 세션을 바꾸면 GT도 바뀝니다.
                </p>
              )}
              {d.personaNarrative && (
                <p className="mt-2 text-[11px] leading-relaxed text-[#868b94]">{d.personaNarrative}</p>
              )}

              <div className="mt-3 grid gap-x-6 gap-y-3 border-t border-[#f1f3f5] pt-3 md:grid-cols-2 lg:grid-cols-3">
                {/* 가치 · 동기 */}
                <div>
                  <div className="text-[11px] font-semibold text-[#787c82]">소비가치 (이 상황에서)</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(gt.valueLevels ?? {}).map(([k, v]: any) => (
                      <span key={k} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${VALUE_CLS[v] ?? "bg-[#f1f3f5] text-[#9aa0a6]"}`}>
                        {k} · {v}
                      </span>
                    ))}
                  </div>
                  <div className="mt-3 text-[11px] font-semibold text-[#787c82]">쇼핑 동기 (이 상황에서)</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {Object.entries(gt.motivationLevels ?? {}).map(([k, v]: any) => (
                      <span key={k} className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${MOT_CLS[v] ?? "bg-[#f1f3f5] text-[#9aa0a6]"}`}>
                        {k}={v}
                      </span>
                    ))}
                  </div>
                </div>

                {/* 이 사람만의 지점 · 말투 */}
                <div>
                  {gt.personaDistinction && (
                    <>
                      <div className="text-[11px] font-semibold text-[#787c82]">이 사람만의 지점</div>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-[#606060]">{gt.personaDistinction}</p>
                    </>
                  )}
                  {gt.speechStyle && (
                    <>
                      <div className="mt-3 text-[11px] font-semibold text-[#787c82]">말투</div>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-[#606060]">{gt.speechStyle}</p>
                    </>
                  )}
                </div>

                {/* 숨은 의도 */}
                <div>
                  <div className="text-[11px] font-semibold text-[#787c82]">숨은 의도</div>
                  <ul className="mt-1 space-y-1">
                    {(gt.hiddenIntentions ?? []).map((h: string, i: number) => (
                      <li key={i} className="rounded-lg bg-[#fbfcfe] px-2.5 py-1.5 text-[11px] leading-relaxed text-[#404040]">
                        {h}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* 상단 — 세션 횡단 기록 (participant로 묶인 멀티 세션, 서술 비교, 판정 없음) */}
            {cross && (
              <div className="card p-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-[#191919]">세션 횡단 기록 — 같은 사람, 다른 상황</h3>
                  {cross.specVersion != null && (
                    <span className="rounded-full bg-[#eef2ff] px-2 py-0.5 text-[10px] font-medium text-[#4338ca]">
                      participant spec v{cross.specVersion}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-[10px] text-[#9aa0a6]">
                  상황마다 주입 GT가 다를 수 있어요(v2). 무엇이 달라지고 무엇이 반복되는지는 직접 비교해 주세요.
                </p>
                <div className="mt-3 grid gap-2 border-t border-[#f1f3f5] pt-3 sm:grid-cols-2">
                  {(cross.perSession ?? []).map((p: any) => (
                    <div key={p.sessionId} className="rounded-lg bg-[#fbfcfe] px-3 py-2 text-[11px]">
                      <div className="font-semibold text-[#404040]">{p.scenarioTitle}</div>
                      <div className="mt-0.5 text-[#606060]">
                        주입 — 가치 {(p.injected?.valueDominant ?? []).join(" · ") || "–"} ·
                        동기 {(p.injected?.motivationHigh ?? []).join(" · ") || "–"}
                      </div>
                      <div className="text-[#606060]">
                        복원 — 가치 {(p.topTraits ?? []).join(" · ") || "–"} ·
                        동기 {(p.topMotivations ?? []).join(" · ") || "–"}
                      </div>
                    </div>
                  ))}
                </div>
                {cross.specMarkdown && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-[11px] font-medium text-[#4338ca] hover:underline">
                      참가자 자연어 명세 보기 (세션 누적 — 반복 패턴의 기억)
                    </summary>
                    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl border border-[#e4e8eb] bg-[#fbfcfe] p-4 text-xs leading-relaxed text-[#404040]">
{cross.specMarkdown}
                    </pre>
                  </details>
                )}
              </div>
            )}

            {/* 하단 — 대화 | 시스템 복원 */}
            <div className="grid gap-4 lg:grid-cols-[1fr_400px]">
              {/* 왼쪽 — 대화 (기존 채팅 UI 그대로) */}
              <div className="card p-4">
                <h3 className="mb-3 text-sm font-semibold">
                  대화{sessions.length > 1 ? ` — 세션 ${sessIdx + 1} (${sess?.scenarioTitle})` : ""}
                </h3>
                <div className="max-h-[44rem] space-y-3 overflow-y-auto pr-1">
                  {(sess?.transcript ?? []).map((item: any, i: number) =>
                    item.kind === "turn" ? (
                      <MessageBubble key={i} turn={item.turn as Turn} />
                    ) : (
                      <div key={i} className="flex justify-end">
                        <div className="inline-block rounded-md bg-violet-50 px-2.5 py-1 text-[11px] text-violet-700">
                          {FB[item.feedbackType] ?? item.feedbackType} — {item.productTitle}
                          {item.reasonText && <span className="text-violet-500"> · &ldquo;{item.reasonText}&rdquo;</span>}
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>

              {/* 오른쪽 — 시스템 복원 */}
              <div className="card p-4">
                <h3 className="text-sm font-bold text-[#191919]">
                  시스템 복원{sessions.length > 1 ? ` — 세션 ${sessIdx + 1}` : ""}
                </h3>
                <div className="mt-1 text-[10px] text-[#9aa0a6]">
                  주입(가치 {(inj.valueDominant ?? []).join("·") || "–"} · 동기 {(inj.motivationHigh ?? []).join("·") || "–"}) ↔ 복원 결과를 직접 비교
                </div>

                <div className="mt-3">
                  <div className="mb-1 text-[11px] font-semibold text-[#787c82]">가치 5축</div>
                  <AnchorRadar scores={rec.anchorScores ?? {}} breakdown={rec.anchorBreakdown ?? {}} size={230} />
                </div>

                {rec.motivationScores && Object.keys(rec.motivationScores).length > 0 && (
                  <div className="mt-3 border-t border-[#f1f3f5] pt-3">
                    <div className="mb-1 text-[11px] font-semibold text-[#787c82]">쇼핑 동기 7축</div>
                    <MotivationRadar scores={rec.motivationScores} size={230} />
                  </div>
                )}

                <div className="mt-3 border-t border-[#f1f3f5] pt-3">
                  <div className="mb-1 text-[11px] font-semibold text-[#787c82]">추출된 의도 ({(rec.topics ?? []).length})</div>
                  <ul className="space-y-1">
                    {(rec.topics ?? []).map((t: any, i: number) => (
                      <li key={i} className="flex items-center gap-1.5 text-[11px]">
                        <span className="flex-1 text-[#404040]">{t.label}</span>
                        {t.kind && (
                          <span className={`rounded px-1 py-0.5 text-[9px] ${KIND_CLS[t.kind] ?? "bg-[#f1f3f5] text-[#868b94]"}`}>
                            {t.kind}
                          </span>
                        )}
                        <span className="rounded bg-[#f1f3f5] px-1 py-0.5 text-[9px] text-[#868b94]">
                          {EXP_KO[t.explicitness] ?? t.explicitness}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </>
        )}
        {personaModal}
      </div>
    );
  }

  // ── 목록 ──────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* 헤더 — 제목 + 통계 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-[#191919]">합성 대화 검수</h2>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-[#606060]">
            LLM User Agent가 페르소나를 연기한 합성 대화입니다. 페르소나에{" "}
            <b className="font-semibold text-[#4f46e5]">주입한 숨은 의도(GT)</b>와 시스템이{" "}
            <b className="font-semibold text-[#191919]">복원한 결과</b>를 나란히 놓고 직접 비교해 보세요.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 text-[11px]">
          <span className="rounded-full bg-[#eef2ff] px-2.5 py-1 font-medium text-[#4338ca]">
            합성 {data.synthesizedCount}/{data.count}
          </span>
          {data.multiSessionCount > 0 && (
            <span className="rounded-full bg-[#ecfdf5] px-2.5 py-1 font-medium text-[#047857]">
              🔗 멀티 {data.multiSessionCount}
            </span>
          )}
        </div>
      </div>

      {/* 범례 — 카드 칩 색을 그대로 키로 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-[#e9ecf1] bg-[#fbfcfe] px-3.5 py-2 text-[11px] text-[#606060]">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm bg-[#4f46e5]" />
          주입 GT <span className="text-[#9aa0a6]">에이전트엔 비공개</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm bg-[#f1f3f5] ring-1 ring-inset ring-[#e4e8eb]" />
          시스템 복원
        </span>
        <span>🔗 멀티 세션 <span className="text-[#9aa0a6]">같은 사람·다른 상황 (v2)</span></span>
        <span className="ml-auto text-[#9aa0a6]">※ 일치 판정은 자동으로 하지 않아요</span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {runs.map((r) => {
          const pending = !r.synthesized;
          const body = (
            <>
              <div className="flex items-center gap-2.5">
                <img src={avatarUrl(r.personaId)} alt="" className="h-10 w-10 shrink-0 rounded-full bg-[#eef2ff]" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-[#191919]">{r.name}</div>
                  <div className="truncate text-xs text-[#9aa0a6]">{r.occupation || "—"}</div>
                </div>
                {r.sessionCount > 1 && (
                  <span className="shrink-0 rounded-full bg-[#ecfdf5] px-2 py-0.5 text-[10px] font-medium text-[#047857]">
                    🔗 {r.sessionCount}세션
                  </span>
                )}
                {pending ? (
                  <span className="shrink-0 rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[10px] font-medium text-[#868b94]">
                    합성 대기
                  </span>
                ) : r.gtVersion === "v2" ? (
                  <span className="shrink-0 rounded-full bg-[#eef2ff] px-2 py-0.5 text-[10px] font-medium text-[#4338ca]">
                    GT v2
                  </span>
                ) : null}
              </div>

              <div className="mt-2 truncate text-[11px] text-[#606060]">
                🛒 {(r.scenarioTitles ?? [r.scenarioTitle ?? r.scenarioId]).filter(Boolean).join(" → ")}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-1 text-[10px]">
                <span className="text-[#9aa0a6]">주입</span>
                {(r.injected?.valueDominant ?? []).length === 0 && <span className="text-[#c8ccd0]">–</span>}
                {(r.injected?.valueDominant ?? []).map((a: string) => (
                  <span key={a} className="rounded bg-[#4f46e5] px-1.5 py-0.5 font-medium text-white">{a}</span>
                ))}
                {(r.injected?.motivationHigh ?? []).map((a: string) => (
                  <span key={a} className="rounded bg-[#eef2ff] px-1.5 py-0.5 font-medium text-[#4338ca]">{a}</span>
                ))}
                {!pending && (
                  <>
                    <span className="ml-1 text-[#c9cdd2]">↔</span>
                    <span className="text-[#9aa0a6]">복원</span>
                    {(r.recoveredTop ?? []).map((a: string) => (
                      <span key={a} className="rounded bg-[#f1f3f5] px-1.5 py-0.5 font-medium text-[#606060]">{a}</span>
                    ))}
                    {(r.topMotivations ?? []).map((a: string) => (
                      <span key={a} className="rounded bg-[#f8f9fa] px-1.5 py-0.5 font-medium text-[#868b94]">{a}</span>
                    ))}
                  </>
                )}
              </div>

              {!pending && (
                <div className="mt-2 flex items-center gap-3 border-t border-[#f1f3f5] pt-2 text-[10px] text-[#9aa0a6]">
                  <span>{r.userTurns}턴</span>
                  <span>의도 {r.topics}개</span>
                  <span>{r.ended === "purchase" ? "🛍 구매" : "탐색 종료"}</span>
                </div>
              )}
            </>
          );
          return pending ? (
            <div key={r.personaId} className="card cursor-default p-3 opacity-60">{body}</div>
          ) : (
            <button
              key={r.personaId}
              onClick={() => setModalId(r.personaId)}
              style={{ transitionProperty: "transform, border-color, box-shadow, scale", transitionDuration: "150ms" }}
              className="card p-3 text-left hover:-translate-y-px hover:border-[#4f46e5] hover:shadow-[0_6px_20px_-6px_rgba(79,70,229,0.25)] active:scale-[0.98]"
            >
              {body}
            </button>
          );
        })}
      </div>

      {personaModal}
    </div>
  );
}
