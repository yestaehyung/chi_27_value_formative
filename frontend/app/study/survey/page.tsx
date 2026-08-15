"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { LIKERT_MID, SurveyQuestion } from "@/lib/survey";
// 본실험 사전 설문 (2026-07-27). FS1의 A–F 설문은 fs1-frozen 브랜치에 그대로 남아 있다 —
// 본실험은 3조건 비교가 목적이라 TCV/동기 프로파일링(D·E)을 재지 않는다.
import {
  PRE_STUDY_LOCALIZED as SURVEY,
  PRE_STUDY_INTRO_LOCALIZED as SURVEY_INTRO,
  PRE_STUDY_REQUIRED_IDS_LOCALIZED as REQUIRED_IDS,
  TEST_SURVEY_SKIP,
  computePreStudyProfile as computeProfile,
  LIKERT_MIN_LOCALIZED as LIKERT_MIN,
  LIKERT_MAX_LOCALIZED as LIKERT_MAX,
  canonicalizeStudyAnswers,
} from "@/lib/localizedMainSurvey";
import { IS_ENGLISH_STUDY, STUDY_UI } from "@/lib/studyI18n";

type Answers = Record<string, string | string[]>;

export default function SurveyPage() {
  const router = useRouter();
  const [answers, setAnswers] = useState<Answers>({});
  const [submitting, setSubmitting] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  const set = (id: string, value: string | string[]) => setAnswers((p) => ({ ...p, [id]: value }));
  const toggleMulti = (id: string, opt: string) =>
    setAnswers((p) => {
      const cur = (p[id] as string[]) || [];
      return { ...p, [id]: cur.includes(opt) ? cur.filter((o) => o !== opt) : [...cur, opt] };
    });

  // 참여 제외 / 필수 미응답
  const excluded = useMemo(
    () => SURVEY.some((s) => s.questions.some((q) => q.excludeIf && answers[q.id] === q.excludeIf)),
    [answers]
  );
  const missing = useMemo(
    () => REQUIRED_IDS.filter((id) => { const v = answers[id]; return v === undefined || v === ""; }),
    [answers]
  );
  // 화면 표시용 전체 누적 문항 번호 (id → 1..N)
  const qNumbers = useMemo(() => {
    const m: Record<string, number> = {};
    let n = 0;
    SURVEY.forEach((s) => s.questions.forEach((q) => { m[q.id] = ++n; }));
    return m;
  }, []);
  const canSubmit = !excluded && missing.length === 0 && !submitting;

  const proceed = async () => {
    setSubmitting(true);
    try {
      const profile = computeProfile(answers);
      const canonicalAnswers = canonicalizeStudyAnswers(answers);
      const res = await api.submitSurvey(canonicalAnswers, profile); // 비어 있어도 참가자 생성(흐름 동일)
      // 배정된 조건을 튜토리얼에 넘긴다 — 조건별로 안내할 단계가 다르다
      // (기준을 안 보여주는 조건에 '기준 확인'을 설명하면 조작이 깨진다).
      // URL이 아니라 sessionStorage로: 주소창·히스토리에 조건 라벨이 보이면
      // 참가자가 자기 조건을 알게 되어 블라인딩이 깨진다.
      if (res.studyCondition) sessionStorage.setItem("vc:studyCond", res.studyCondition);
      router.push(`/study/tutorial?pid=${res.participantId}`);
    } catch (e) {
      console.error(e);
      setSubmitting(false);
      alert(STUDY_UI.survey.submitError);
    }
  };
  const submit = () => {
    if (excluded || missing.length > 0) { setShowErrors(true); return; }
    proceed();
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-32">
      <div>
        <h1 className="text-xl font-bold">{STUDY_UI.survey.title}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">{SURVEY_INTRO}</p>
      </div>

      {SURVEY.map((section) => (
        <section key={section.id} className="card space-y-5 p-5">
          <div>
            <h2 className="text-sm font-bold text-[#4f46e5]">{section.title}</h2>
            {section.desc && <p className="mt-1 text-xs text-slate-500">{section.desc}</p>}
          </div>
          {section.questions.map((q) => (
            <Question
              key={q.id}
              q={q}
              num={qNumbers[q.id]}
              value={answers[q.id]}
              showError={showErrors}
              onSingle={(v) => set(q.id, v)}
              onMulti={(opt) => toggleMulti(q.id, opt)}
              onText={(v) => set(q.id, v)}
            />
          ))}
        </section>
      ))}

      {/* sticky 제출 바 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#e9ecef] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs">
            {excluded ? (
              <span className="font-semibold text-rose-600">{STUDY_UI.survey.ineligible}</span>
            ) : missing.length > 0 ? (
              <span className="text-slate-500">{STUDY_UI.survey.requiredRemaining(missing.length)}</span>
            ) : (
              <span className="text-emerald-600">{STUDY_UI.survey.ready}</span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {TEST_SURVEY_SKIP && (
              <button
                onClick={proceed}
                disabled={submitting}
                title={STUDY_UI.survey.skipTitle}
                className="rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs text-slate-500 transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40 enabled:active:scale-[0.96]"
              >
                {STUDY_UI.survey.skip}
              </button>
            )}
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="btn btn-primary px-5 py-2 disabled:opacity-40"
            >
              {submitting ? STUDY_UI.survey.submitting : STUDY_UI.survey.submit}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Question({
  q, num, value, showError, onSingle, onMulti, onText,
}: {
  q: SurveyQuestion;
  num: number;
  value: string | string[] | undefined;
  showError: boolean;
  onSingle: (v: string) => void;
  onMulti: (opt: string) => void;
  onText: (v: string) => void;
}) {
  const isMissing = showError && q.required && (value === undefined || value === "");
  const excludedHere = q.excludeIf && value === q.excludeIf;

  return (
    <div className={`-m-2 rounded-lg p-2 transition-colors duration-200 ${isMissing ? "bg-rose-50" : "bg-transparent"}`}>
      <label className="block text-sm font-medium text-[#191919]">
        <span className="mr-1 text-slate-400">{num}.</span>{q.label}
        {q.required && <span className="ml-1 text-rose-500">*</span>}
      </label>

      {q.type === "likert" && (
        <div className="mt-2">
          <div className="flex gap-1.5">
            {[1, 2, 3, 4, 5, 6, 7].map((n) => {
              const on = value === String(n);
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => onSingle(String(n))}
                  className={`h-10 flex-1 rounded-md border text-sm font-semibold tabular-nums transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.96] ${
                    on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                  }`}
                >
                  {n}
                </button>
              );
            })}
          </div>
          {/* 버튼과 동일한 7칸 그리드 — 가운데 라벨이 4번 버튼 바로 아래 중앙에 오게 */}
          <div className="mt-1 grid grid-cols-7 gap-1.5 text-[10px] text-slate-400">
            <span className="col-start-1 text-left">{LIKERT_MIN}</span>
            <span className="col-start-4 text-center">{IS_ENGLISH_STUDY ? "Neutral" : LIKERT_MID}</span>
            <span className="col-start-7 text-right">{LIKERT_MAX}</span>
          </div>
        </div>
      )}

      {q.type === "single" && (
        <div className="mt-2 space-y-1.5">
          {q.options!.map((opt) => {
            const on = value === opt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onSingle(opt)}
                className={`block w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors duration-150 active:scale-[0.99] ${
                  on ? "border-[#4f46e5] bg-[#eef2ff] font-medium" : "border-[#e4e8eb] hover:border-[#4f46e5]"
                }`}
              >
                {opt}
              </button>
            );
          })}
          {excludedHere && <p className="text-xs text-rose-500">{STUDY_UI.survey.responseExcluded}</p>}
        </div>
      )}

      {q.type === "multi" && (
        <div className="mt-2 flex flex-wrap gap-2">
          {q.options!.map((opt) => {
            const on = ((value as string[]) || []).includes(opt);
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onMulti(opt)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.96] ${
                  on ? "border-[#4f46e5] bg-[#4f46e5] text-white" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      )}

      {q.type === "text" && (
        <input
          value={(value as string) || ""}
          onChange={(e) => onText(e.target.value)}
          placeholder={q.placeholder}
          className="mt-2 w-full rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
        />
      )}

      {q.type === "textlong" && (
        <textarea
          value={(value as string) || ""}
          onChange={(e) => onText(e.target.value)}
          placeholder={q.placeholder}
          rows={3}
          className="mt-2 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-sm focus:border-[#4f46e5] focus:outline-none"
        />
      )}
    </div>
  );
}
