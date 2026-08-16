"use client";

// 제품군별 지식 행렬 (2026-08-13, 측정 계획 §4) — 카테고리 확정 직후 · 첫 쇼핑 전 1회.
//
// 네 제품군 각각에 대해: 주관적 지식 5문항(Flynn & Goldsmith 1999, 2·4·5 역채점)
// + 구매 경험 1 + 초기 기준 명확성 1 + 자유응답(현재 생각하는 기준).
// 과제마다 묻지 않고 여기서 한 번에 받는 이유: 과제 직전에 물으면 직전 과제 경험이
// 오염시키고, 대화 시작 후에 물으면 "초기" 상태가 아니게 된다.
//
// 자유응답은 기준 감사(precision/recall)의 사전 기준선이 된다 — 대화 전에 무엇을
// 알고 있었는지가 여기 잠긴다.
import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import MainSurveyForm from "@/components/study/MainSurveyForm";
import {
  KNOWLEDGE_SECTIONS_LOCALIZED, TEST_SURVEY_SKIP, computeKnowledgeScore,
  fillTemplate, canonicalizeStudyAnswerValue } from "@/lib/localizedMainSurvey";
import { allQuestions, type MSection } from "@/lib/mainSurvey";
import { nextTask, queuedTasks } from "@/lib/taskQueue";
import { STUDY_UI, categoryLabel, tr } from "@/lib/studyI18n";

function KnowledgeInner() {
  const router = useRouter();
  const params = useSearchParams();
  const pid = params.get("pid") ?? "";
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [missing, setMissing] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  // 큐의 4개 카테고리 — 표시 순서는 친숙(1단계 선택) 먼저, 과제 순서와 무관.
  const categories = useMemo(() => {
    const tasks = queuedTasks(pid || undefined);
    const familiar = tasks.filter((t) => t.familiarity === "familiar").map((t) => t.category);
    const unfamiliar = tasks.filter((t) => t.familiarity !== "familiar").map((t) => t.category);
    return [...familiar, ...unfamiliar];
  }, [pid]);

  // 큐가 없으면(직접 URL 진입·세션 유실) 카테고리 선택부터 다시.
  useEffect(() => {
    if (categories.length === 0) router.replace(pid ? `/study/categories?pid=${pid}` : "/study/categories");
  }, [categories, router, pid]);

  // 카테고리별 섹션 — 문항 id를 "k:{카테고리}:" 프리픽스로 유일화한다.
  const sectionsByCategory = useMemo(
    () => categories.map((cat) => {
      const filled = fillTemplate(KNOWLEDGE_SECTIONS_LOCALIZED, { category: categoryLabel(cat) });
      const prefixed: MSection[] = filled.map((sec) => ({
        ...sec,
        id: `${sec.id}:${cat}`,
        questions: sec.questions.map((q) => ({ ...q, id: `k:${cat}:${q.id}` })),
      }));
      return { cat, sections: prefixed };
    }),
    [categories],
  );

  const requiredIds = useMemo(
    () => sectionsByCategory.flatMap(({ sections }) =>
      allQuestions(sections).filter((q) => q.type !== "text").map((q) => q.id)),
    [sectionsByCategory],
  );

  const startFirstTask = async () => {
    const task = nextTask(pid || undefined);
    if (!task) return;
    const res = await api.createCategorySession(task.category, task.familiarity, pid || undefined);
    router.push(`/study/session/${res.sessionId}`);
  };

  const submit = async () => {
    const miss = requiredIds.filter((id) => !answers[id]);
    if (miss.length > 0) { setMissing(miss); return; }
    setSubmitting(true);
    try {
      const scores: Record<string, number> = {};
      for (const cat of categories) {
        const s = computeKnowledgeScore(answers, `k:${cat}:`);
        if (s !== null) scores[cat] = s;
      }
      // EN 모드: 표시값(영어 선택지)을 정본(한국어 선택지)으로 변환해 저장 — id가
      // k:{카테고리}:{문항id} 접두형이라 내부 문항 id로 벗겨서 매핑한다.
      const canonicalAnswers = Object.fromEntries(
        Object.entries(answers).map(([k, v]) => {
          const innerId = k.split(":").pop() ?? k;
          return [k, canonicalizeStudyAnswerValue(innerId, v)];
        }),
      );
      if (pid) await api.submitKnowledgeSurvey(pid, canonicalAnswers, scores, categories);
      await startFirstTask();
    } catch (e) {
      console.error(e);
      alert(STUDY_UI.survey.submitError);
      setSubmitting(false);
    }
  };

  const skip = async () => {
    setSubmitting(true);
    try { await startFirstTask(); } catch (e) { console.error(e); setSubmitting(false); }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 pb-32 pt-2">
      <div>
        <h1 className="text-xl font-bold">{tr("고른 상품군에 대해 알려주세요", "About the Categories You Chose")}</h1>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          {tr(
            "쇼핑을 시작하기 전에, 고른 네 상품군 각각에 대한 지금의 생각을 알려주세요. 정답은 없어요.",
            "Before you start shopping, tell us what you currently think about each of the four categories you chose. There are no right answers.",
          )}
        </p>
      </div>

      {sectionsByCategory.map(({ cat, sections }) => (
        <section key={cat} className="card space-y-4 p-5">
          <MainSurveyForm
            sections={sections}
            answers={answers}
            onChange={(id, v) => setAnswers((p) => ({ ...p, [id]: v }))}
            missingIds={missing}
          />
        </section>
      ))}

      {/* sticky 제출 바 */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-[#e9ecef] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <div className="text-xs">
            {missing.length > 0 ? (
              <span className="font-semibold text-rose-600">{STUDY_UI.survey.requiredRemaining(missing.length)}</span>
            ) : (
              <span className="tabular-nums text-slate-400">
                {requiredIds.filter((id) => answers[id]).length} / {requiredIds.length}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {TEST_SURVEY_SKIP && (
              <button
                onClick={skip}
                disabled={submitting}
                className="rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs text-slate-500 transition-colors duration-150 hover:border-[#4f46e5] hover:text-[#4f46e5] disabled:opacity-40"
              >
                {STUDY_UI.survey.skip}
              </button>
            )}
            <button onClick={submit} disabled={submitting} className="btn btn-primary px-5 py-2 disabled:opacity-40">
              {submitting ? STUDY_UI.survey.submitting : tr("제출하고 첫 쇼핑 시작", "Submit and Start Shopping")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  return (
    <Suspense fallback={null}>
      <KnowledgeInner />
    </Suspense>
  );
}
