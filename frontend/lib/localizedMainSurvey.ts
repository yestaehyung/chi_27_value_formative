import {
  ALLOWS_CORRECTION, AUDIT_INFLUENCE, AUDIT_NECESSITY, CRITERION_CHECK,
  CRITERION_CHECK_MAX, CRITERION_CHECK_MIN, INFERS_INTENTION, KNOWLEDGE_SECTIONS,
  LIKERT_MAX, LIKERT_MIN, POST_STUDY, POST_TASK, PRE_STUDY, PRE_STUDY_INTRO,
  PRE_STUDY_REQUIRED_IDS, SHOWS_CRITERIA, TEST_SURVEY_SKIP,
  computeKnowledgeScore, computePreStudyProfile, computeSectionScores,
  fillTemplate, postStudySectionsFor,
  type MSection, type StudyCondition,
} from "./mainSurvey";
import {
  AUDIT_INFLUENCE_EN, AUDIT_NECESSITY_EN, CRITERION_CHECK_EN,
  KNOWLEDGE_SECTIONS_EN, LIKERT_MAX_EN, LIKERT_MIN_EN, POST_STUDY_EN,
  POST_TASK_EN, PRE_STUDY_EN, PRE_STUDY_INTRO_EN, PRE_STUDY_REQUIRED_IDS_EN,
} from "./mainSurvey.en";
import { IS_ENGLISH_STUDY } from "./studyI18n";

export {
  ALLOWS_CORRECTION, CRITERION_CHECK_MAX, CRITERION_CHECK_MIN,
  INFERS_INTENTION, SHOWS_CRITERIA, TEST_SURVEY_SKIP,
  computeKnowledgeScore, computePreStudyProfile, computeSectionScores, fillTemplate,
};
export type { StudyCondition };

export const LIKERT_MIN_LOCALIZED = IS_ENGLISH_STUDY ? LIKERT_MIN_EN : LIKERT_MIN;
export const LIKERT_MAX_LOCALIZED = IS_ENGLISH_STUDY ? LIKERT_MAX_EN : LIKERT_MAX;
export const PRE_STUDY_LOCALIZED = IS_ENGLISH_STUDY ? PRE_STUDY_EN : PRE_STUDY;
export const PRE_STUDY_INTRO_LOCALIZED = IS_ENGLISH_STUDY ? PRE_STUDY_INTRO_EN : PRE_STUDY_INTRO;
export const PRE_STUDY_REQUIRED_IDS_LOCALIZED = IS_ENGLISH_STUDY ? PRE_STUDY_REQUIRED_IDS_EN : PRE_STUDY_REQUIRED_IDS;
export const KNOWLEDGE_SECTIONS_LOCALIZED = IS_ENGLISH_STUDY ? KNOWLEDGE_SECTIONS_EN : KNOWLEDGE_SECTIONS;
export const POST_TASK_LOCALIZED = IS_ENGLISH_STUDY ? POST_TASK_EN : POST_TASK;
export const CRITERION_CHECK_LOCALIZED = IS_ENGLISH_STUDY ? CRITERION_CHECK_EN : CRITERION_CHECK;
export const AUDIT_NECESSITY_LOCALIZED = IS_ENGLISH_STUDY ? AUDIT_NECESSITY_EN : AUDIT_NECESSITY;
export const AUDIT_INFLUENCE_LOCALIZED = IS_ENGLISH_STUDY ? AUDIT_INFLUENCE_EN : AUDIT_INFLUENCE;

/** 종료 설문 — 세 조건 공통 (2026-08-13). 로케일만 고른다. */
export function postStudySectionsLocalized(condition: StudyCondition | null | undefined): MSection[] {
  const allowed = new Set(postStudySectionsFor(condition).map((section) => section.id));
  const sections = IS_ENGLISH_STUDY ? POST_STUDY_EN : POST_STUDY;
  return sections.filter((section) => allowed.has(section.id));
}

const CANONICAL_QUESTION_BY_ID = new Map(
  [...PRE_STUDY, ...KNOWLEDGE_SECTIONS, ...POST_TASK, ...POST_STUDY]
    .flatMap((section) => section.questions)
    .concat(CRITERION_CHECK)
    .map((question) => [question.id, question]),
);

const ENGLISH_QUESTION_BY_ID = new Map(
  [...PRE_STUDY_EN, ...KNOWLEDGE_SECTIONS_EN, ...POST_TASK_EN, ...POST_STUDY_EN]
    .flatMap((section) => section.questions)
    .concat(CRITERION_CHECK_EN)
    .map((question) => [question.id, question]),
);

/**
 * Convert an English display choice back to the existing canonical Korean
 * value before persistence. Question IDs and numeric Likert values remain
 * unchanged, so exports from Korean and English deployments stay comparable.
 */
export function canonicalizeStudyAnswerValue<T>(questionId: string, value: T): T {
  if (!IS_ENGLISH_STUDY || typeof value !== "string") return value;
  const english = ENGLISH_QUESTION_BY_ID.get(questionId);
  const canonical = CANONICAL_QUESTION_BY_ID.get(questionId);
  if (!english?.options || !canonical?.options) return value;
  const optionIndex = english.options.indexOf(value);
  return (optionIndex >= 0 ? (canonical.options[optionIndex] ?? value) : value) as T;
}

/** 응답 묶음 전체를 정본(한국어) 선택지 값으로 변환해 저장한다. */
export function canonicalizeStudyAnswers<T extends Record<string, unknown>>(answers: T): T {
  if (!IS_ENGLISH_STUDY) return answers;
  const out: Record<string, unknown> = {};
  for (const [id, value] of Object.entries(answers)) {
    out[id] = canonicalizeStudyAnswerValue(id, value);
  }
  return out as T;
}
