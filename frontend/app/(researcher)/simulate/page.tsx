"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Persona, Scenario, Turn } from "@/lib/types";
import MessageBubble from "@/components/chat/MessageBubble";
import AnchorRadar from "@/components/preference/AnchorRadar";
import SynthesisReview from "@/components/synthesis/SynthesisReview";

const avatarUrl = (seed: string) =>
  `https://api.dicebear.com/9.x/notionists/svg?seed=${encodeURIComponent(seed)}`;

// 10개 삶의 단면 내러티브 — 모달 오른쪽에 라벨 섹션으로 표시
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

export default function SimulatePage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [scenarioId, setScenarioId] = useState("gift_for_other");
  const [personaId, setPersonaId] = useState("");
  const [query, setQuery] = useState("");
  const [maxTurns, setMaxTurns] = useState(6);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [view, setView] = useState<"run" | "synth">("run");

  useEffect(() => {
    api.scenarios().then((d) => {
      setScenarios(d.scenarios);
      // 기본 시나리오를 현재 seed의 offered 목록으로 맞춘다 — 옛 기본값 'gift_for_other'가
      // seed_naver엔 없어 "scenario not resolvable" 400 나던 것 방지.
      setScenarioId((cur) =>
        d.scenarios?.some((s: Scenario) => s.id === cur) ? cur : (d.scenarios?.[0]?.id || cur)
      );
    }).catch(console.error);
    api.personas().then((d) => {
      setPersonas(d.personas);
      if (d.personas?.length) setPersonaId((cur) => cur || d.personas[0].id);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDetailOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = async () => {
    if (!personaId) return;
    setRunning(true);
    setResult(null);
    setDetailOpen(false);
    try {
      // 선택한 persona로 LLM 합성(숨은 의도 GT 주입)을 백그라운드 시작 → 끝날 때까지 폴링.
      // 실 LLM이라 수 분 소요 — 한 번에 전체 배치를 돌리지 않고 이 페르소나 한 명만.
      await api.runSynthesis(personaId, scenarioId, maxTurns);
      for (let i = 0; i < 160; i++) {            // 상한 ~8분 (3s × 160)
        await new Promise((r) => setTimeout(r, 3000));
        const st = await api.synthesisRunStatus(personaId);
        if (!st.running) break;
      }
      setView("synth");                          // 결과는 '합성 대화 보기'에서 (DB에서 로드 — 주입 GT ↔ 복원)
    } catch (e) {
      console.error(e);
      alert("합성 실행 실패: " + (e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  const persona = personas.find((p) => p.id === personaId);
  const pd = persona?.demographics ?? {};
  const pnar = persona?.narratives ?? {};
  const chips = (persona
    ? [
        [pd.province, pd.district].filter(Boolean).join(" · "),
        pd.education_level, pd.marital_status, pd.family_type, pd.housing_type, pd.bachelors_field,
      ]
    : []
  ).filter(Boolean) as string[];
  const lastSnapshot = result?.preferenceSnapshots?.at(-1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return personas;
    return personas.filter((p) => {
      const d = p.demographics || {};
      return [p.name, d.occupation, d.province, d.district, String(d.age ?? "")]
        .some((s) => String(s || "").toLowerCase().includes(q));
    });
  }, [personas, query]);

  return (
    <>
      <div className="space-y-6">
      <div className="msg-in">
        <h1 className="text-xl font-bold text-balance">합성 데이터 생성 시뮬레이션</h1>
        <p className="mt-1 text-sm text-slate-500">
          합성 사용자(User Agent)와 Service Agent가 자동으로 대화해 합성 대화·온톨로지 데이터를 생성합니다.
          User Agent는 숨은 의도(ground truth)를 갖고 반응하고, Service Agent가 그 의도를 얼마나 잘 추론하는지를 evaluation으로 평가합니다.
        </p>
      </div>

      {/* 모드 전환: 직접 실행(온디맨드) ↔ 합성 대화 배치 검수 */}
      <div className="msg-in inline-flex rounded-xl border border-[#e4e8eb] bg-white p-1 text-sm" style={{ animationDelay: "60ms" }}>
        {([["run", "▶ 직접 실행"], ["synth", "🧪 합성 대화 보기"]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setView(k)}
            className={`rounded-lg px-4 py-1.5 font-medium transition-colors duration-150 active:scale-[0.96] ${
              view === k ? "bg-[#4f46e5] text-white" : "text-[#606060] hover:text-[#191919]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {view === "run" ? (
      <>

      {/* 실행 설정 + 선택된 페르소나 */}
      <div className="msg-in card p-5" style={{ animationDelay: "120ms" }}>
        <div className="flex flex-wrap items-end gap-4">
          <div className="min-w-[220px] flex-1">
            <label className="text-xs font-medium text-slate-500">시나리오</label>
            <select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none">
              {scenarios.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select>
          </div>
          <div className="w-28">
            <label className="text-xs font-medium text-slate-500">최대 user turn</label>
            <input type="number" min={2} max={16} value={maxTurns}
                   onChange={(e) => setMaxTurns(Number(e.target.value))}
                   className="mt-1 w-full rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none" />
          </div>
          <button onClick={run} disabled={running || !personaId}
                  className="btn btn-primary h-[38px] px-5 disabled:opacity-50">
            {running ? "합성 중… (수 분)" : "▶ 시뮬레이션 실행"}
          </button>
        </div>

        {persona && (
          <div className="mt-4 flex items-center gap-3 border-t border-[#eef0f2] pt-4">
            <img src={avatarUrl(persona.id)} alt="" className="h-11 w-11 shrink-0 rounded-full bg-[#eef2ff] outline outline-1 -outline-offset-1 outline-black/10" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-[#191919]">
                {persona.name}
                <span className="ml-1.5 font-normal text-[#868b94]">{pd.age}세 · {pd.sex}</span>
              </div>
              <div className="truncate text-xs text-[#606060]">
                {[pd.occupation, pd.province].filter(Boolean).join(" · ")}
              </div>
            </div>
            <button onClick={() => setDetailOpen(true)}
                    className="btn h-[34px] shrink-0 px-3 text-xs">자세히 보기 →</button>
          </div>
        )}
      </div>

      {/* 페르소나 선택 그리드 (Nemotron-Personas-Korea) */}
      <div className="msg-in card p-5" style={{ animationDelay: "180ms" }}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">
            페르소나 선택{" "}
            <span className="font-normal text-[#b0b8c1]">· {filtered.length}/{personas.length}</span>
          </h2>
          <input value={query} onChange={(e) => setQuery(e.target.value)}
                 placeholder="🔍 이름·직업·지역 검색"
                 className="w-56 rounded-lg border border-[#e4e8eb] px-3 py-1.5 text-sm focus:border-[#4f46e5] focus:outline-none" />
        </div>

        <div className="max-h-[460px] overflow-y-auto p-1">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((p) => {
              const d = p.demographics || {};
              const sel = p.id === personaId;
              return (
                <button
                  key={p.id}
                  onClick={() => (sel ? setDetailOpen(true) : setPersonaId(p.id))}
                  title={sel ? "한 번 더 클릭 → 자세히 보기" : ""}
                  style={{ transitionProperty: "color, background-color, border-color, box-shadow, scale", transitionDuration: "150ms" }}
                  className={`rounded-xl border p-3 text-left active:scale-[0.98] ${
                    sel
                      ? "border-[#4f46e5] bg-[#eef2ff] ring-1 ring-[#4f46e5]"
                      : "border-[#e4e8eb] bg-white hover:border-[#4f46e5] hover:bg-[#fafbff]"
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <img src={avatarUrl(p.id)} alt="" className="h-10 w-10 shrink-0 rounded-full bg-[#eef2ff] outline outline-1 -outline-offset-1 outline-black/10" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1.5">
                        <span className="truncate font-semibold text-[#191919]">{p.name}</span>
                        <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-medium ${
                          sel ? "bg-white text-[#4f46e5]" : "bg-[#f1f3f5] text-[#868b94]"
                        }`}>
                          {d.age}{(d.sex || "").slice(0, 1)}
                        </span>
                      </div>
                      <div className="truncate text-xs text-[#606060]">{d.occupation || "—"}</div>
                    </div>
                  </div>
                  <div className="mt-1.5 truncate text-[11px] text-[#9aa0a6]">
                    {[d.province, d.district].filter(Boolean).join(" · ")}
                    {sel && <span className="ml-1 font-semibold text-[#4f46e5]">· ✓ 선택됨</span>}
                  </div>
                </button>
              );
            })}
          </div>
          {filtered.length === 0 && (
            <p className="py-8 text-center text-sm text-[#9aa0a6]">검색 결과가 없습니다.</p>
          )}
        </div>
      </div>

      {result && (
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <div className="card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">대화 로그</h2>
              <Link href={`/research/session/${result.sessionId}`}
                    className="text-xs text-emerald-600 hover:underline">
                연구자 뷰에서 자세히 보기 →
              </Link>
            </div>
            <div className="max-h-[32rem] space-y-3 overflow-y-auto">
              {result.turns.map((t: Turn) => <MessageBubble key={t.id} turn={t} showMeta />)}
            </div>
          </div>

          <div className="space-y-4">
            <div className="card p-4">
              <h2 className="text-sm font-semibold">Evaluation</h2>
              <dl className="mt-2 space-y-1.5 text-xs">
                {Object.entries(result.evaluation).map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-slate-50 pb-1">
                    <dt className="text-slate-500">{k}</dt>
                    <dd className="font-mono font-medium tabular-nums">{v === null ? "–" : String(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>

            {lastSnapshot && (
              <div className="card p-4">
                <h2 className="text-sm font-semibold">최종 anchor 분포</h2>
                <AnchorRadar scores={lastSnapshot.anchorScores} />
                <div className="mt-2 text-xs text-slate-500">
                  {lastSnapshot.userVisibleSummary?.oneSentenceSummary}
                </div>
              </div>
            )}

            <div className="card p-4 text-xs text-slate-600">
              <h2 className="text-sm font-semibold text-slate-800">생성된 데이터</h2>
              <ul className="mt-2 space-y-1">
                <li>피드백 이벤트: <b>{result.feedbackEvents.length}</b>개</li>
                <li>chosen-rejected pair: <b>{result.pairs.length}</b>개</li>
                <li>preference snapshot: <b>{result.preferenceSnapshots.length}</b>개</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      </>
      ) : (
        <SynthesisReview />
      )}
      </div>

      {/* 페르소나 상세 모달 (좌: 정체성 · 우: 10 내러티브) — space-y-6 바깥에 둬야
          fixed inset-0가 margin-top 없이 전체 화면(navbar 포함)을 덮는다 */}
      {detailOpen && persona && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => setDetailOpen(false)}>
          <div className="flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-[#e4e8eb] px-5 py-3">
              <h3 className="text-sm font-semibold">페르소나 상세</h3>
              <button onClick={() => setDetailOpen(false)} aria-label="닫기"
                      className="-mr-2 flex h-10 w-10 items-center justify-center rounded-lg text-lg leading-none text-[#9aa0a6] transition-colors duration-150 hover:bg-[#f0f2f4] hover:text-[#191919] active:scale-[0.92]">✕</button>
            </div>

            <div className="grid flex-1 grid-cols-1 overflow-hidden sm:grid-cols-[230px_1fr]">
              {/* 왼쪽 — 정체성 */}
              <div className="flex flex-col gap-3 border-b border-[#e4e8eb] p-5 sm:border-b-0 sm:border-r">
                <img src={avatarUrl(persona.id)} alt=""
                     className="h-24 w-24 rounded-2xl bg-[#eef2ff] outline outline-1 -outline-offset-1 outline-black/10" />
                <div>
                  <div className="text-lg font-bold text-[#191919]">{persona.name}</div>
                  <div className="text-sm text-[#606060]">
                    {[pd.age && `${pd.age}세`, pd.sex, pd.occupation].filter(Boolean).join(" · ")}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {chips.map((c, i) => (
                    <span key={i} className="rounded-full bg-[#f1f3f5] px-2 py-0.5 text-[11px] text-[#606060]">{c}</span>
                  ))}
                </div>
                <p className="text-xs leading-relaxed text-[#868b94]">{persona.personaNarrative}</p>
                <button onClick={run} disabled={running || !personaId}
                        className="btn btn-primary mt-auto w-full disabled:opacity-50">
                  {running ? "합성 중… (수 분)" : "▶ 이 페르소나로 실행"}
                </button>
              </div>

              {/* 오른쪽 — 10 내러티브 (2열 그리드, 스크롤) */}
              <div className="grid content-start gap-x-6 gap-y-3.5 overflow-y-auto p-5 md:grid-cols-2">
                {FACETS.filter(([k]) => pnar[k]).map(([k, icon, label]) => (
                  <div key={k}>
                    <div className="text-xs font-semibold text-[#404040]">{icon} {label}</div>
                    <p className="mt-0.5 text-xs leading-relaxed text-[#606060]">{pnar[k]}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
