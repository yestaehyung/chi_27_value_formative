"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { SURVEY, LIKERT_MIN, LIKERT_MID, LIKERT_MAX } from "@/lib/survey";

type ParticipantRow = {
  id: string;
  label: string | null;
  sessionCount: number;
  hasSurvey: boolean;
  surveyCount: number;
  createdAt: string;
};

type SurveyData = {
  participantId: string;
  label: string | null;
  answers: Record<string, string | string[]>;
  profile: Record<string, number>;
  createdAt: string;
};

// 파생 점수 한글 라벨 (survey.ts SCORING 키 기준)
const PROFILE_LABELS: Record<string, string> = {
  Functional: "기능적 가치",
  Social: "사회적 가치",
  Emotional: "정서적 가치",
  Epistemic: "탐색적 가치",
  Conditional: "상황적 가치",
  Utilitarian: "실용적 동기",
  Hedonic: "쾌락적 동기",
  CorrectabilityNeed: "수정 가능성 요구",
  PrivacyConcern: "프라이버시 우려",
};

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  } catch {
    return iso;
  }
}

export default function ResearchSurveysPage() {
  const [participants, setParticipants] = useState<ParticipantRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [survey, setSurvey] = useState<SurveyData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.participants().then((d) => setParticipants(d.participants || [])).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selected) { setSurvey(null); return; }
    setLoading(true);
    api.participantSurvey(selected)
      .then(setSurvey)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selected]);

  const withSurvey = useMemo(() => participants.filter((p) => p.hasSurvey), [participants]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">사전 설문 응답</h1>
        <div className="flex flex-wrap gap-2">
          <Link href="/research/sessions" className="btn">← 세션 목록</Link>
        </div>
      </div>
      <p className="text-xs text-slate-500">
        참가자가 제출한 FS1 사전 설문을 열람합니다. 응답은 설문 정의(섹션 A–F) 순서로 표시됩니다.
      </p>

      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        {/* 좌: 참가자 선택 */}
        <div className="card h-fit p-3">
          <div className="mb-2 px-1 text-xs font-bold text-slate-500">
            설문 완료 참가자 <span className="text-[#4f46e5]">{withSurvey.length}</span>
          </div>
          <ul className="space-y-1">
            {withSurvey.map((p) => {
              const on = p.id === selected;
              return (
                <li key={p.id}>
                  <button
                    onClick={() => setSelected(p.id)}
                    className={`block w-full rounded-lg border px-3 py-2 text-left transition-colors ${
                      on ? "border-[#4f46e5] bg-[#eef2ff]" : "border-[#e4e8eb] hover:border-[#4f46e5]"
                    }`}
                  >
                    <div className="text-sm font-medium text-[#191919]">{p.label || p.id}</div>
                    <div className="mt-0.5 text-[11px] text-slate-400">
                      {p.surveyCount}개 응답 · 세션 {p.sessionCount} · {fmtDate(p.createdAt)}
                    </div>
                  </button>
                </li>
              );
            })}
            {withSurvey.length === 0 && (
              <li className="px-2 py-8 text-center text-xs text-slate-400">
                아직 설문을 제출한 참가자가 없어요.<br />
                <Link href="/study/survey" className="text-[#4f46e5] underline">사전 설문</Link>을 작성하면 여기 나타납니다.
              </li>
            )}
          </ul>
        </div>

        {/* 우: 선택한 참가자의 응답 */}
        <div className="space-y-4">
          {!selected && (
            <div className="card px-5 py-16 text-center text-sm text-slate-400">
              왼쪽에서 참가자를 선택하세요.
            </div>
          )}
          {loading && <div className="card px-5 py-16 text-center text-sm text-slate-400">불러오는 중…</div>}

          {survey && !loading && (
            <>
              <div className="card p-5">
                <h2 className="text-base font-bold text-[#191919]">{survey.label || survey.participantId}</h2>
                <p className="mt-0.5 font-mono text-[11px] text-slate-400">{survey.participantId} · {fmtDate(survey.createdAt)}</p>

                {/* 파생 점수 (가치·동기) */}
                {Object.keys(survey.profile).length > 0 && (
                  <div className="mt-4">
                    <div className="mb-2 text-xs font-bold text-slate-500">파생 점수 (1–7 평균)</div>
                    <div className="space-y-1.5">
                      {Object.entries(survey.profile).map(([k, v]) => (
                        <div key={k} className="flex items-center gap-2">
                          <div className="w-28 shrink-0 text-xs text-[#606060]">{PROFILE_LABELS[k] || k}</div>
                          <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                            <div className="h-full rounded-full bg-[#4f46e5]" style={{ width: `${(Number(v) / 7) * 100}%` }} />
                          </div>
                          <div className="w-8 shrink-0 text-right font-mono text-xs text-[#4f46e5]">{Number(v).toFixed(1)}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* 문항별 응답 — 설문 정의 순서 */}
              {SURVEY.map((section) => {
                const answered = section.questions.filter((q) => {
                  const a = survey.answers[q.id];
                  return a !== undefined && a !== "" && !(Array.isArray(a) && a.length === 0);
                });
                if (answered.length === 0) return null;
                return (
                  <div key={section.id} className="card p-5">
                    <h3 className="text-sm font-bold text-[#4f46e5]">{section.title}</h3>
                    <dl className="mt-3 space-y-3">
                      {section.questions.map((q) => {
                        const a = survey.answers[q.id];
                        const empty = a === undefined || a === "" || (Array.isArray(a) && a.length === 0);
                        return (
                          <div key={q.id} className="border-b border-slate-50 pb-3 last:border-0 last:pb-0">
                            <dt className="text-xs text-slate-500">{q.label}</dt>
                            <dd className={`mt-1 text-sm ${empty ? "text-slate-300" : "text-[#191919]"}`}>
                              {empty ? "—"
                                : q.type === "likert"
                                  ? `${a} / 7 (${LIKERT_MIN} … ${LIKERT_MID} … ${LIKERT_MAX})`
                                  : Array.isArray(a) ? a.join(", ") : String(a)}
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
