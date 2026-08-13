// 본실험 설문 정의 — 2026-08-13 최종 측정 계획 반영 (docs/briefs 참조 문서).
//
// 측정 구조 (검증 척도 기반):
//   1. PRE_STUDY          실험 전 1회 — 동의 + 인구통계 + 사실 공변량
//   2. KNOWLEDGE_SECTIONS 카테고리 확정 직후 1회 — 제품군별 주관적 지식(Flynn &
//                         Goldsmith 1999, 5문항) + 구매경험 + 초기 기준 명확성 + 자유응답
//   3. POST_TASK          각 과제 후 — Choice Confidence 3문항 (Heitmann et al. 2007)
//                         ※ 원척도는 9점이나 설문 내 일관성을 위해 7점으로 조정(adapted)
//   4. 기준 감사          각 과제, 최종 선택·확신 응답 후 — A파트(내 기준 나열) →
//                         B파트(추론 기준 대조: CRITERION_CHECK) + 누락 추가
//   5. POST_STUDY         네 과제 종료 후 1회 — CRS-Que 4종(이해·투명성·통제감·만족)
//                         + S-TIAS(신뢰) + Intention to Use. **세 조건 공통** —
//                         기능이 없어서 낮게 나오는 것 자체가 조건 간 결과다.
//
// 결정 사항 (2026-08-13): Purchase Intention 삭제(Intention to Use와 중복),
// 인구통계 추가, 조건별 섹션 필터 제거, Choice Confidence 7점 통일.
// 원척도 문항 수는 줄이지 않고, referent(에이전트명 등)만 맥락에 맞게 바꾼다.

export type MQType = "single" | "likert" | "text";

export type MQuestion = {
  id: string;
  label: string;
  type: MQType;
  options?: string[]; // single
  /** 리커트 양 끝 라벨. 생략 시 기본(전혀 그렇지 않다 ~ 매우 그렇다) */
  minLabel?: string;
  maxLabel?: string;
  /** 역문항 — 구인 평균 계산 시 (8 - v)로 뒤집는다 */
  reverse?: boolean;
  /** 미응답이면 제출 불가 (참여 동의 문항) */
  required?: boolean;
  /** 이 값을 고르면 연구 참여 제외 */
  excludeIf?: string;
  /** text 전용 — 입력 안내 */
  placeholder?: string;
};

export type MSection = {
  id: string;
  title: string;
  desc?: string;
  questions: MQuestion[];
};

/** 테스트용 설문 건너뛰기 노출 여부 — ⚠️ 본실험 모집 시작 전 반드시 false로.
 *  건너뛴 설문은 저장되지 않는다 (새로고침 시 다시 뜸). */
export const TEST_SURVEY_SKIP = true;

export const LIKERT_POINTS = 7;
export const LIKERT_MIN = "전혀 그렇지 않다";
export const LIKERT_MAX = "매우 그렇다";

/** 7점 리커트 (기본 앵커) */
const lk = (id: string, label: string, reverse = false): MQuestion =>
  ({ id, label, type: "likert", ...(reverse ? { reverse } : {}) });
/** 객관식 */
const sg = (id: string, label: string, options: string[]): MQuestion =>
  ({ id, label, type: "single", options });
/** 참여 동의/자격 — 미응답이면 제출 불가, `no`를 고르면 참여 제외 */
const consent = (id: string, label: string): MQuestion =>
  ({ id, label, type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" });

// ─────────────────────────────────────────────────────────────────────
// 1. 실험 전 설문 (참가자 1회) — 동의 + 인구통계 + 사실 기반 공변량
// ─────────────────────────────────────────────────────────────────────
export const PRE_STUDY_INTRO =
  "본 설문은 대화형 쇼핑 에이전트 연구의 사전 설문입니다. 정답은 없으며, 평소 경험에 " +
  "가장 가까운 답을 선택해 주세요. 소요 시간은 약 2분입니다.";

export const PRE_STUDY: MSection[] = [
  {
    id: "consent",
    title: "참여 기준 및 동의",
    desc: "연구 참여 가능 여부를 확인합니다.",
    questions: [
      consent("PRE_C1", "만 19세 이상인가요?"),
      consent("PRE_C2", "최근 3개월 이내 온라인 쇼핑을 한 적이 있나요?"),
      consent("PRE_C3", "대화 로그, 클릭·선택·거절 행동, 설문 응답이 연구 목적으로 기록될 수 있음에 동의하나요?"),
    ],
  },
  {
    id: "demographics",
    title: "기본 정보",
    questions: [
      sg("DEM_AGE", "연령대를 선택해 주세요.", [
        "만 19–24세", "25–29세", "30–34세", "35–39세", "40–49세", "50세 이상",
      ]),
      sg("DEM_GENDER", "성별을 선택해 주세요.", [
        "여성", "남성", "기타/응답하지 않음",
      ]),
      sg("DEM_JOB", "현재 직업 상태를 선택해 주세요.", [
        "학생", "직장인", "자영업/프리랜서", "주부", "무직/구직 중", "기타",
      ]),
    ],
  },
  {
    // 다문항 잠재변수 척도가 아니라 문항별 공변량 (측정 계획 §3)
    id: "shopping_facts",
    title: "쇼핑 경험",
    questions: [
      sg("FACT_SHOP_FREQ", "최근 3개월 동안 온라인에서 상품을 구매하거나 상품을 비교한 빈도는 어느 정도입니까?", [
        "전혀 없음", "월 1회 미만", "월 1–3회", "주 1–2회", "주 3회 이상",
      ]),
      sg("FACT_AI_REC", "ChatGPT, Claude, Gemini 등 생성형 AI에게 상품 추천이나 구매 관련 조언을 요청한 빈도는 어느 정도입니까?", [
        "경험 없음", "1–2회", "3–5회", "월 1–3회", "주 1회 이상",
      ]),
      lk("FACT_COMPARE", "나는 상품을 구매하기 전에 여러 후보를 비교하는 편이다."),
    ],
  },
];

export const PRE_STUDY_REQUIRED_IDS = allQuestions(PRE_STUDY)
  .filter((q) => q.required)
  .map((q) => q.id);

/** 사전 설문 파생 — 리커트가 1문항뿐이라 섹션 평균은 참고용 */
export function computePreStudyProfile(answers: Record<string, unknown>): Record<string, number> {
  return computeSectionScores(PRE_STUDY, answers);
}

// ─────────────────────────────────────────────────────────────────────
// 2. 제품군별 지식 행렬 (카테고리 확정 직후 1회 · {category} 치환)
// ─────────────────────────────────────────────────────────────────────
// Subjective Product Knowledge — Flynn & Goldsmith (1999) 5문항 전체, 2·4·5 역채점.
// 구매경험·초기 명확성은 사실/상태 문항이라 지식 점수와 합산하지 않는다.
export const KNOWLEDGE_SECTIONS: MSection[] = [
  {
    id: "subjective_knowledge",
    title: "“{category}”에 대한 지식",
    questions: [
      lk("SPK_1", '나는 "{category}"에 대해 꽤 많이 알고 있다.'),
      lk("SPK_2", '나는 "{category}"에 대해 잘 알고 있다고 느끼지 않는다.', true),
      lk("SPK_3", '내 친구들 사이에서 나는 "{category}"에 대한 ‘전문가’ 중 한 명이다.'),
      lk("SPK_4", '대부분의 사람들과 비교하면, 나는 "{category}"에 대해 덜 알고 있다.', true),
      lk("SPK_5", '"{category}"에 관해서라면 나는 정말 많이 알지 못한다.', true),
      sg("EXP_BUY", '"{category}" 상품을 직접 구매해 본 경험은 몇 회입니까?', [
        "구매 경험 없음", "1회", "2–3회", "4회 이상",
      ]),
      lk("INIT_CLARITY", '현재 나는 "{category}" 상품을 고를 때 무엇을 중요하게 보아야 할지 명확히 알고 있다.'),
      {
        id: "INIT_CRITERIA_FREE",
        type: "text",
        label: '현재 "{category}" 상품을 고를 때 중요하다고 생각하는 조건이나 기준을 모두 적어 주세요.',
        placeholder: "예: 예산 10만원 이내, 무게, 디자인… 아직 정하지 못했다면 “미정”",
      },
    ],
  },
];

/** 지식 5문항(역채점 반영) 평균 — 제품군별 조절변수 점수 */
export function computeKnowledgeScore(answers: Record<string, unknown>, prefix: string): number | null {
  const items = KNOWLEDGE_SECTIONS[0].questions.filter((q) => q.id.startsWith("SPK_"));
  const vals: number[] = [];
  for (const q of items) {
    const v = Number(answers[`${prefix}${q.id}`]);
    if (!Number.isFinite(v) || v <= 0) continue;
    vals.push(q.reverse ? LIKERT_POINTS + 1 - v : v);
  }
  return vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100 : null;
}

// ─────────────────────────────────────────────────────────────────────
// 3. 각 과제 후 — Choice Confidence (Heitmann, Lehmann, & Herrmann 2007)
// ─────────────────────────────────────────────────────────────────────
// 원척도 9점 → 설문 내 일관성을 위해 7점으로 조정(adapted). 1번 역채점.
// 최종 선택 직후·기준 감사 화면을 보여주기 **전에** 응답한다.
export const POST_TASK: MSection[] = [
  {
    id: "choice_confidence",
    title: "최종 선택에 대한 확신",
    desc: "방금 마친 쇼핑에서의 선택을 떠올리며 답해 주세요.",
    questions: [
      lk("CC_1", "어떤 상품이 내 선호에 가장 잘 맞는지 확신하는 것은 불가능했다.", true),
      lk("CC_2", "내 선호에 가장 잘 맞는 상품 하나를 골라낼 때 확신이 있었다."),
      lk("CC_3", "내 필요를 가장 잘 충족하는 상품을 찾았다고 확신한다."),
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────
// 4. 기준 감사 (Participant Criterion Audit) — 과제마다, 확신 응답 후
// ─────────────────────────────────────────────────────────────────────
// A파트: 에이전트 기준을 **보여주기 전** 참가자의 실제 기준을 잠근다 —
// 이 순서가 precision/recall 계산의 오염을 막는다 (뒤로 돌아갈 수 없음).
export const AUDIT_NECESSITY = ["반드시 충족", "가능하면 충족", "최종적으로 중요하지 않음"] as const;
export const AUDIT_INFLUENCE = ["예", "아니오", "판단하기 어려움"] as const;

// B파트: 에이전트가 추론한 기준마다 2문항 (일치 + 형성 시점 5택).
export const CRITERION_CHECK: MQuestion[] = [
  sg("CRIT_MATCH", "에이전트가 표시한 이 기준은 실제 나의 구매 기준과 얼마나 일치합니까?", [
    "정확히 일치", "일부만 일치하며 수정 필요", "내 기준이 아님",
  ]),
  sg("CRIT_FORMATION", "이 기준은 언제부터 중요했습니까?", [
    "대화 전부터 중요했고 처음부터 말했다",
    "대화 전부터 중요했지만 처음에는 말하지 않았다",
    "상품이나 비교 정보를 본 뒤 대화 중 새로 중요해졌다",
    "에이전트가 제안한 뒤 중요하다고 받아들였다",
    "실제로는 내 기준이 아니다",
  ]),
];

/** 검증 대상으로 제시할 추론 기준 개수 상한 (주요 기준 3–5개) */
export const CRITERION_CHECK_MAX = 5;
export const CRITERION_CHECK_MIN = 3;

// ─────────────────────────────────────────────────────────────────────
// 5. 네 과제 종료 후 (참가자 1회 · 6구성개념 × 3문항 · 세 조건 공통)
// ─────────────────────────────────────────────────────────────────────
export const POST_STUDY: MSection[] = [
  {
    // CRS-Que (Jin et al. 2024) — CUI Understanding (원: Borsci et al. 2022)
    id: "understanding",
    title: "에이전트의 이해",
    questions: [
      lk("CUI_1", "이 쇼핑 에이전트는 내가 말한 내용을 이해했다."),
      lk("CUI_2", "나는 이 쇼핑 에이전트가 내가 원하는 것을 이해했다고 느꼈다."),
      lk("CUI_3", "나는 이 쇼핑 에이전트가 내 구매 의도를 이해했다고 느꼈다."),
    ],
  },
  {
    // CRS-Que — Transparency (원: Hellmann et al. 2022; Pu et al. 2011)
    id: "transparency",
    title: "투명성",
    questions: [
      lk("TR_1", "나는 왜 이 상품들이 추천되었는지 이해했다."),
      lk("TR_2", "나는 시스템이 상품의 적합성을 어떻게 판단했는지 이해했다."),
      lk("TR_3", "나는 추천 결과가 내 선호와 얼마나 잘 맞는지 이해했다."),
    ],
  },
  {
    // CRS-Que — User Control (개념 원출처: Pu et al. 2011)
    id: "control",
    title: "사용자 통제감",
    questions: [
      lk("UC_1", "나는 이 쇼핑 에이전트를 사용하여 내 선호를 수정하는 과정을 통제할 수 있다고 느꼈다."),
      lk("UC_2", "나는 이 쇼핑 에이전트가 나에게 제시하는 추천을 통제할 수 있었다."),
      lk("UC_3", "나는 내 선호에 따라 추천 결과를 조정하는 과정을 통제할 수 있다고 느꼈다."),
    ],
  },
  {
    // CRS-Que — Satisfaction
    id: "satisfaction",
    title: "추천 만족도",
    questions: [
      lk("SAT_1", "나는 이 쇼핑 에이전트가 제공한 추천에 만족했다."),
      lk("SAT_2", "이 쇼핑 에이전트의 추천 결과는 만족스러웠다."),
      lk("SAT_3", "이 쇼핑 에이전트의 추천은 전반적으로 나를 만족시켰다."),
    ],
  },
  {
    // S-TIAS (McGrath et al. 2025; 원척도 Jian et al. 2000)
    id: "trust",
    title: "AI 쇼핑 에이전트 신뢰",
    questions: [
      lk("TRUST_1", "나는 이 AI 쇼핑 에이전트에 대해 확신을 갖는다."),
      lk("TRUST_2", "이 AI 쇼핑 에이전트는 신뢰할 만하다."),
      lk("TRUST_3", "나는 이 AI 쇼핑 에이전트를 신뢰할 수 있다."),
    ],
  },
  {
    // CRS-Que — Intention to Use (개념 원출처: Pu et al. 2011)
    id: "intention",
    title: "재사용 의향",
    questions: [
      lk("ITU_1", "나는 이 쇼핑 에이전트를 다시 사용할 것이다."),
      lk("ITU_2", "나는 이 쇼핑 에이전트를 자주 사용할 것이다."),
      lk("ITU_3", "나는 친구들에게 이 쇼핑 에이전트에 대해 이야기할 것이다."),
    ],
  },
];

// 조건별 UI 게이트 (백엔드 app/core/conditions.py와 짝)
export type StudyCondition = "baseline1" | "baseline2" | "ours";

export const INFERS_INTENTION: Record<StudyCondition, boolean> = {
  baseline1: false, baseline2: true, ours: true,
};
export const SHOWS_CRITERIA: Record<StudyCondition, boolean> = {
  baseline1: false, baseline2: false, ours: true,
};
export const ALLOWS_CORRECTION: Record<StudyCondition, boolean> = {
  baseline1: false, baseline2: false, ours: true,
};

/** 종료 설문은 **세 조건 공통** (2026-08-13 확정) — 기능이 없는 조건에서 통제감이
 *  낮게 나오는 것은 "물을 수 없음"이 아니라 조건 간 결과다. 필터 없이 전체를 준다. */
export function postStudySectionsFor(_condition: StudyCondition | null | undefined): MSection[] {
  return POST_STUDY;
}

// ─────────────────────────────────────────────────────────────────────
// 헬퍼
// ─────────────────────────────────────────────────────────────────────

/** {category} 같은 자리표시자를 치환한 섹션 사본 */
export function fillTemplate(sections: MSection[], vars: Record<string, string>): MSection[] {
  const sub = (s: string) => s.replace(/\{(\w+)\}/g, (m, k) => vars[k] ?? m);
  return sections.map((sec) => ({
    ...sec,
    title: sub(sec.title),
    desc: sec.desc ? sub(sec.desc) : undefined,
    questions: sec.questions.map((q) => ({ ...q, label: sub(q.label) })),
  }));
}

export function allQuestions(sections: MSection[]): MQuestion[] {
  return sections.flatMap((s) => s.questions);
}

/** 리커트 문항만 대상으로 섹션별 평균. reverse 문항은 (8 - v)로 뒤집는다.
 *  구성개념은 각각 보고하며 전체 합산 점수는 만들지 않는다 (측정 계획 §10). */
export function computeSectionScores(
  sections: MSection[],
  answers: Record<string, unknown>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const sec of sections) {
    const vals: number[] = [];
    for (const q of sec.questions) {
      if (q.type !== "likert") continue;
      const v = Number(answers[q.id]);
      if (!Number.isFinite(v) || v <= 0) continue;
      vals.push(q.reverse ? LIKERT_POINTS + 1 - v : v);
    }
    if (vals.length) {
      out[sec.id] = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
    }
  }
  return out;
}
