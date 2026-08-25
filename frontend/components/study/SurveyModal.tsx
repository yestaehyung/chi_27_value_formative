"use client";

// 본실험 설문 모달 — 과제 직전 / 과제 직후 / 전체 종료 세 도구가 공유한다.
// 이 문항들은 전부 종속변인이라 기본값은 "전 문항 필수"다. 빠진 응답은 조건 간 비교에서
// 그 참가자 전체를 빼야 하므로, 건너뛰기는 명시적으로 허용할 때만 노출한다.
import { useMemo, useState } from "react";

import { allQuestions, computeSectionScores, type MSection } from "@/lib/mainSurvey";
import MainSurveyForm from "@/components/study/MainSurveyForm";
import { STUDY_UI, tr } from "@/lib/studyI18n";
import { canonicalizeStudyAnswers } from "@/lib/localizedMainSurvey";

export default function SurveyModal({
  title,
  desc,
  sections,
  submitLabel = STUDY_UI.surveyModal.submit,
  onSubmit,
  onSkip,
  submitting = false,
}: {
  title: string;
  desc?: string;
  sections: MSection[];
  submitLabel?: string;
  onSubmit: (answers: Record<string, string>, profile: Record<string, number>) => void;
  /** 넘기면 '건너뛰기'가 보인다. 본실험 기본 운영에선 넘기지 않는다. */
  onSkip?: () => void;
  submitting?: boolean;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [showErrors, setShowErrors] = useState(false);

  const questionIds = useMemo(() => allQuestions(sections).map((q) => q.id), [sections]);
  const missing = useMemo(
    () => questionIds.filter((id) => !answers[id]),
    [questionIds, answers],
  );

  const submit = () => {
    if (missing.length > 0) {
      setShowErrors(true);
      // 첫 미응답 문항으로 스크롤 — 긴 설문에서 "어디가 빠졌는지" 못 찾는 이탈 방지
      document.getElementById(`q-${missing[0]}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    onSubmit(canonicalizeStudyAnswers(answers), computeSectionScores(sections, answers));
  };

  const answered = questionIds.length - missing.length;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="card flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden"
      >
        <div className="border-b border-[#f0f2f4] px-5 py-4 sm:px-6">
          <h2 className="text-base font-bold text-[#191919]">{title}</h2>
          {desc && <p className="mt-1 text-xs leading-relaxed text-[#9aa0a6]">{desc}</p>}
          <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-[#f0f2f4]">
            <div
              className="h-full rounded-full bg-[#4f46e5] transition-[width] duration-300"
              style={{ width: `${(answered / Math.max(1, questionIds.length)) * 100}%` }}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          {/* id는 미응답 스크롤 타깃 — MainSurveyForm 바깥에서 감싼다 */}
          <div>
            {sections.map((sec, si) => (
              <div key={sec.id} className="mb-5 last:mb-0">
                {/* 긴 설문에서 "얼마나 남았나" — 헤더 진행 바(문항 단위)에 더해
                    섹션 단위 위치도 보여준다 (2026-08-25 QA: 6화면 분량 피로). */}
                {sections.length > 1 && (
                  <div className="mb-1 text-[10px] font-semibold tabular-nums text-slate-400">
                    {si + 1} / {sections.length}
                  </div>
                )}
                <MainSurveyForm
                  sections={[sec]}
                  answers={answers}
                  onChange={(id, v) => setAnswers((p) => ({ ...p, [id]: v }))}
                  missingIds={showErrors ? missing : []}
                />
                {sec.questions.map((q) => (
                  <span key={q.id} id={`q-${q.id}`} className="sr-only" />
                ))}
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#f0f2f4] px-5 py-3 sm:px-6">
          <div className="text-xs">
            {showErrors && missing.length > 0 ? (
              <span className="font-semibold text-rose-600">
                {tr(`${missing.length}개 문항이 남았어요.`, `${missing.length} ${missing.length === 1 ? "question remains" : "questions remain"}.`)}
              </span>
            ) : onSkip ? (
              <button
                onClick={onSkip}
                disabled={submitting}
                className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline disabled:opacity-40"
              >
                {STUDY_UI.survey.skip}
              </button>
            ) : (
              <span className="tabular-nums text-slate-400">
                {answered} / {questionIds.length}
              </span>
            )}
          </div>
          <button onClick={submit} disabled={submitting} className="btn btn-primary px-5 py-2">
            {submitting ? STUDY_UI.surveyModal.submitting : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
