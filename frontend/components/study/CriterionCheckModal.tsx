"use client";

// 구매 기준 감사 (Participant Criterion Audit) — 측정 계획 §7.1 (2026-08-13 개편).
//
// 3단계, **순서 강제** (A로 되돌아갈 수 없음):
//   A. 에이전트의 기준을 보여주기 **전** — 내가 실제로 쓴 기준을 자유 나열하고
//      기준마다 필수성·영향을 답한다. 여기서 참가자의 기준이 잠긴다 —
//      에이전트 추론을 먼저 보면 precision/recall 계산이 오염된다.
//   B. 에이전트가 추론한 기준을 하나씩 보여주며 일치(3택)·형성 시점(5택)을 묻는다.
//      추론이 없는 조건(baseline1)은 이 단계가 자동 생략된다.
//   C. 에이전트가 표시하지 않았지만 실제 사용한 기준 표시(A 목록에서 선택 + 추가).
import { useMemo, useState } from "react";

import {
  AUDIT_INFLUENCE_LOCALIZED, AUDIT_NECESSITY_LOCALIZED, canonicalAuditValue,
  CRITERION_CHECK_LOCALIZED as CRITERION_CHECK,
} from "@/lib/localizedMainSurvey";
import { QuestionRow } from "@/components/study/MainSurveyForm";
import { tr } from "@/lib/studyI18n";

export type CriterionCandidate = {
  topic: { id: string; label: string; priority?: string | null };
  evidence: { id: string; type: string; quote?: string; role?: string; productTitle?: string; feedbackType?: string }[];
};

export type OwnCriterion = { label: string; necessity?: string; influence?: string };

export type CriterionAnswer = {
  topicId: string;
  topicLabel: string;
  matches?: string;
  formation?: string;
};

/** 화면 표기 → 저장 값 (분석 시 문자열 비교가 깨지지 않게 짧은 키로 박제) */
const MATCH_CODE: Record<string, string> = {
  "정확히 일치": "일치",
  "일부만 일치하며 수정 필요": "부분일치",
  "내 기준이 아님": "기준아님",
  "Matches exactly": "일치",
  "Partially matches; needs revision": "부분일치",
  "Not my criterion": "기준아님",
};

const FORMATION_CODE: Record<string, string> = {
  "대화 전부터 중요했고 처음부터 말했다": "처음부터_말함",
  "대화 전부터 중요했지만 처음에는 말하지 않았다": "처음부터_미표현",
  "상품이나 비교 정보를 본 뒤 대화 중 새로 중요해졌다": "대화중_새로형성",
  "에이전트가 제안한 뒤 중요하다고 받아들였다": "에이전트_제안수용",
  "실제로는 내 기준이 아니다": "내기준아님",
  "Important before the conversation, and I stated it from the start": "처음부터_말함",
  "Important before the conversation, but I did not state it at first": "처음부터_미표현",
  "Became important during the conversation after seeing products or comparisons": "대화중_새로형성",
  "I adopted it after the agent suggested it": "에이전트_제안수용",
  "It is not actually my criterion": "내기준아님",
};

function EvidenceList({ items }: { items: CriterionCandidate["evidence"] }) {
  if (!items.length) {
    return <p className="text-[11px] text-slate-400">{tr("이 기준에 연결된 근거 기록이 없습니다.", "No evidence is recorded for this criterion.")}</p>;
  }
  return (
    <ul className="space-y-1.5">
      {items.slice(0, 4).map((e) => (
        <li key={e.id} className="rounded-md bg-white px-2.5 py-1.5 text-[11px] leading-relaxed text-slate-600">
          <span className="mr-1.5 rounded bg-[#eef2ff] px-1.5 py-0.5 text-[10px] font-semibold text-[#4f46e5]">
            {e.type === "turn" ? (e.role === "user" ? tr("내 발화", "Your message") : tr("에이전트", "Agent")) : e.type === "feedback" ? tr("상품 반응", "Product feedback") : tr("상품 특성", "Product attribute")}
          </span>
          {e.type === "feedback" && e.productTitle ? (
            <span>
              <b>{e.productTitle}</b>
              {e.feedbackType ? ` — ${e.feedbackType === "like" ? tr("좋아요", "Like") : e.feedbackType === "dislike" ? tr("싫어요", "Dislike") : e.feedbackType}` : ""}
              {e.quote ? ` · “${e.quote}”` : ""}
            </span>
          ) : (
            <span>{e.quote || tr("(내용 없음)", "(No content)")}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A파트 한 기준의 보조 선택지 (필수성·영향) — 짧은 세그먼트 버튼 */
function SegmentPick({ label, options, value, onChange }: {
  label: string; options: readonly string[]; value?: string; onChange: (v: string) => void;
}) {
  return (
    <div className="mt-1.5">
      <div className="text-[10.5px] text-[#9aa0a6]">{label}</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {options.map((opt) => {
          const on = value === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              aria-pressed={on}
              className={`rounded-md border px-2 py-1 text-[11px] transition-[color,background-color,border-color] duration-150 ${
                on ? "border-[#4f46e5] bg-[#eef2ff] font-semibold text-[#4f46e5]" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
              }`}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function CriterionCheckModal({
  candidates,
  onSubmit,
  onSkip,
  submitting = false,
}: {
  candidates: CriterionCandidate[];
  onSubmit: (items: CriterionAnswer[], ownCriteria: OwnCriterion[], missingCriteria: string[]) => void;
  /** 테스트용 건너뛰기 (TEST_SURVEY_SKIP) — 응답 저장 없이 닫는다 */
  onSkip?: () => void;
  submitting?: boolean;
}) {
  const [step, setStep] = useState<"A" | "B" | "C">("A");
  // A파트
  const [own, setOwn] = useState<OwnCriterion[]>([]);
  const [draft, setDraft] = useState("");
  // B파트
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [showErrors, setShowErrors] = useState(false);
  // C파트
  const [missingPicked, setMissingPicked] = useState<Set<number>>(new Set());
  const [extraMissing, setExtraMissing] = useState("");

  const current = candidates[idx];
  const currentAnswers = answers[current?.topic.id ?? ""] ?? {};
  const missingB = useMemo(
    () => CRITERION_CHECK.filter((q) => !currentAnswers[q.id]).map((q) => q.id),
    [currentAnswers],
  );
  const isLastB = idx === candidates.length - 1;
  const ownComplete = own.length > 0 && own.every((c) => c.necessity && c.influence);

  const addOwn = () => {
    const label = draft.trim();
    if (!label) return;
    setOwn((prev) => [...prev, { label }]);
    setDraft("");
  };

  const finishA = () => setStep(candidates.length > 0 ? "B" : "C");

  const nextB = () => {
    if (missingB.length > 0) { setShowErrors(true); return; }
    setShowErrors(false);
    if (!isLastB) { setIdx((i) => i + 1); return; }
    setStep("C");
  };

  const submitAll = () => {
    const items: CriterionAnswer[] = candidates.map((c) => {
      const a = answers[c.topic.id] ?? {};
      const raw = a["CRIT_FORMATION"];
      return {
        topicId: c.topic.id,
        topicLabel: c.topic.label,
        matches: a["CRIT_MATCH"] ? (MATCH_CODE[a["CRIT_MATCH"]] ?? a["CRIT_MATCH"]) : undefined,
        formation: raw ? (FORMATION_CODE[raw] ?? raw) : undefined,
      };
    });
    const missing = [
      ...own.filter((_, i) => missingPicked.has(i)).map((c) => c.label),
      ...extraMissing.split("\n").map((s) => s.trim()).filter(Boolean),
    ];
    const ownCanonical = own.map((c) => ({
      ...c,
      necessity: canonicalAuditValue("necessity", c.necessity),
      influence: canonicalAuditValue("influence", c.influence),
    }));
    onSubmit(items, ownCanonical, missing);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4">
      <div className="card flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden">
        <div className="border-b border-[#f0f2f4] px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-bold text-[#191919]">
              {step === "A"
                ? tr("내가 사용한 구매 기준", "The Criteria You Actually Used")
                : step === "B"
                  ? tr("에이전트가 추론한 기준 확인", "Review the Agent's Inferred Criteria")
                  : tr("빠진 기준 확인", "Criteria the Agent Missed")}
            </h2>
            {step === "B" && (
              <span className="tabular-nums text-xs text-slate-400">{idx + 1} / {candidates.length}</span>
            )}
          </div>
          {step === "A" && (
            <p className="mt-1 text-[11.5px] leading-relaxed text-[#9aa0a6]">
              {tr(
                "방금 상품을 선택하거나 후보를 좁힐 때 실제로 사용한 기준을 모두 적어 주세요. 다음 단계에서 에이전트가 추론한 기준과 비교합니다 — 지금 적은 내용은 이후 바꿀 수 없어요.",
                "List every criterion you actually used to choose or narrow down products. In the next step you will compare them with the agent's inferences — you cannot edit this list afterwards.",
              )}
            </p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          {step === "A" && (
            <>
              <div className="flex gap-1.5">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) { e.preventDefault(); addOwn(); } }}
                  placeholder={tr("예: 예산 10만원 이내, 배터리 오래감…", "e.g., budget under KRW 150,000, long battery life…")}
                  className="min-w-0 flex-1 rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs focus:border-[#4f46e5] focus:outline-none"
                />
                <button onClick={addOwn} disabled={!draft.trim()} className="btn btn-primary shrink-0 px-3 py-2 text-xs">
                  {tr("추가", "Add")}
                </button>
              </div>

              <div className="mt-3 space-y-2.5">
                {own.length === 0 && (
                  <p className="text-[11px] text-slate-400">{tr("기준을 하나씩 추가해 주세요.", "Add your criteria one by one.")}</p>
                )}
                {own.map((c, i) => (
                  <div key={i} className="rounded-xl border border-[#e8eaed] bg-[#fafbfc] px-3 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-semibold text-[#191919]">{c.label}</span>
                      <button
                        onClick={() => setOwn((prev) => prev.filter((_, j) => j !== i))}
                        className="shrink-0 text-[11px] text-[#b0b8c1] hover:text-rose-500"
                      >
                        {tr("삭제", "Remove")}
                      </button>
                    </div>
                    <SegmentPick
                      label={tr("이 기준은 반드시 충족되어야 했습니까?", "Did this criterion have to be met?")}
                      options={AUDIT_NECESSITY_LOCALIZED}
                      value={c.necessity}
                      onChange={(v) => setOwn((prev) => prev.map((x, j) => (j === i ? { ...x, necessity: v } : x)))}
                    />
                    <SegmentPick
                      label={tr("최종 선택·제외에 실제로 영향을 주었습니까?", "Did it actually influence your final selection or exclusion?")}
                      options={AUDIT_INFLUENCE_LOCALIZED}
                      value={c.influence}
                      onChange={(v) => setOwn((prev) => prev.map((x, j) => (j === i ? { ...x, influence: v } : x)))}
                    />
                  </div>
                ))}
              </div>
            </>
          )}

          {step === "B" && current && (
            <>
              <div className="rounded-lg border border-[#e4e8eb] bg-[#f8f9fa] p-3">
                <div className="text-[11px] font-semibold text-[#9aa0a6]">{tr("에이전트가 추론한 기준", "Criterion inferred by the agent")}</div>
                <div className="mt-1 text-sm font-bold leading-relaxed text-[#191919]">{current.topic.label}</div>
                <div className="mt-2.5 text-[11px] font-semibold text-[#9aa0a6]">{tr("이렇게 판단한 근거", "Supporting evidence")}</div>
                <div className="mt-1"><EvidenceList items={current.evidence} /></div>
              </div>
              <div className="mt-4 space-y-3.5">
                {CRITERION_CHECK.map((q) => (
                  <QuestionRow
                    key={q.id}
                    q={q}
                    value={currentAnswers[q.id]}
                    onChange={(v) => setAnswers((p) => ({ ...p, [current.topic.id]: { ...(p[current.topic.id] ?? {}), [q.id]: v } }))}
                    invalid={showErrors && missingB.includes(q.id)}
                  />
                ))}
              </div>
            </>
          )}

          {step === "C" && (
            <>
              <p className="text-xs leading-relaxed text-[#404040]">
                {tr(
                  "에이전트가 표시하지 않았지만 실제 선택에 사용한 기준이 있습니까? 앞에서 적은 기준 중 해당하는 것을 모두 선택하고, 필요하면 추가해 주세요.",
                  "Were there criteria you actually used that the agent did not show? Select all that apply from your list, and add more if needed.",
                )}
              </p>
              <div className="mt-3 space-y-1.5">
                {own.map((c, i) => {
                  const on = missingPicked.has(i);
                  return (
                    <button
                      key={i}
                      onClick={() => setMissingPicked((prev) => {
                        const next = new Set(prev);
                        if (next.has(i)) next.delete(i); else next.add(i);
                        return next;
                      })}
                      aria-pressed={on}
                      className={`block w-full rounded-lg border px-3 py-2 text-left text-xs transition-[color,background-color,border-color] duration-150 ${
                        on ? "border-[#4f46e5] bg-[#eef2ff] font-semibold text-[#4f46e5]" : "border-[#e4e8eb] text-slate-600 hover:border-[#4f46e5]"
                      }`}
                    >
                      {c.label}
                    </button>
                  );
                })}
              </div>
              <textarea
                value={extraMissing}
                onChange={(e) => setExtraMissing(e.target.value)}
                rows={2}
                placeholder={tr("그 외 빠진 기준이 있으면 한 줄에 하나씩 적어 주세요 (없으면 비워두세요)", "Add any other missed criteria, one per line (leave empty if none)")}
                className="mt-3 w-full resize-none rounded-lg border border-[#e4e8eb] px-3 py-2 text-xs leading-relaxed focus:border-[#4f46e5] focus:outline-none"
              />
            </>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[#f0f2f4] px-5 py-3 sm:px-6">
          <div className="text-xs">
            {step === "A" && onSkip ? (
              <button onClick={onSkip} disabled={submitting} className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline disabled:opacity-40">
                {tr("건너뛰기", "Skip")}
              </button>
            ) : step === "A" ? (
              <button onClick={finishA} className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline">
                {tr("사용한 기준이 없어요", "I did not use any criteria")}
              </button>
            ) : step === "B" && showErrors && missingB.length > 0 ? (
              <span className="font-semibold text-rose-600">
                {tr(`${missingB.length}개 문항이 남았어요.`, `${missingB.length} ${missingB.length === 1 ? "question remains" : "questions remain"}.`)}
              </span>
            ) : step === "B" && idx > 0 ? (
              <button
                onClick={() => { setShowErrors(false); setIdx((i) => i - 1); }}
                disabled={submitting}
                className="text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline disabled:opacity-40"
              >
                {tr("이전 기준", "Previous Criterion")}
              </button>
            ) : null}
          </div>
          {step === "A" ? (
            <button onClick={finishA} disabled={!ownComplete || submitting} className="btn btn-primary px-5 py-2 disabled:opacity-40">
              {tr("다음", "Next")}
            </button>
          ) : step === "B" ? (
            <button onClick={nextB} disabled={submitting} className="btn btn-primary px-5 py-2">
              {isLastB ? tr("다음", "Next") : tr("다음 기준", "Next Criterion")}
            </button>
          ) : (
            <button onClick={submitAll} disabled={submitting} className="btn btn-primary px-5 py-2">
              {submitting ? tr("제출 중…", "Submitting…") : tr("제출하고 마치기", "Submit and Finish")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
