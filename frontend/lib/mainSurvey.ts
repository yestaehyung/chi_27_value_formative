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

export type MQType = "single" | "likert" | "slider" | "text";

export type MQuestion = {
  id: string;
  label: string;
  type: MQType;
  options?: string[]; // single
  /** 리커트 양 끝 라벨. 생략 시 기본(전혀 그렇지 않다 ~ 매우 그렇다) */
  minLabel?: string;
  maxLabel?: string;
  /** 역문항 — 구인 평균 계산 시 (points+1 - v)로 뒤집는다 */
  reverse?: boolean;
  /** 리커트 점수 범위 (기본 LIKERT_POINTS=7). CC는 원척도 9점. */
  points?: number;
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
export const TEST_SURVEY_SKIP = false;

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
        "경험 없음", "1에서 2회", "3에서 5회", "월 1에서 3회", "주 1회 이상",
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
        "구매 경험 없음", "1회", "2에서 3회", "4회 이상",
      ]),
      lk("INIT_CLARITY", '현재 나는 "{category}" 상품을 고를 때 무엇을 중요하게 보아야 할지 명확히 알고 있다.'),
      // INIT_CRITERIA_FREE 제거 (2026-08-24 동결 문서 P0-4) — 사전 기준 나열은 아직
      // 표현되지 않은 기준을 강제로 명시하게 해 연구하려는 현상 자체를 바꾼다.
      // 초기 표현의 기준선은 첫 발화·초기 대화 로그로 잡는다.
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
// 원척도 9점 그대로 사용 (2026-08-24 동결 문서 — adapted 7점을 원척도로 복원). 1번 역채점.
// "하나의 상품을 최종 선택했다" 과제에만 제시 — 그 외 상태는 NA (게이팅은 VariantSession).
// 최종 선택 직후·기준 감사 화면을 보여주기 **전에** 응답한다.
export const POST_TASK: MSection[] = [
  {
    id: "choice_confidence",
    title: "최종 선택에 대한 확신",
    desc: "방금 마친 쇼핑에서의 선택을 떠올리며 답해 주세요.",
    questions: [
      { ...lk("CC_1", "어떤 상품이 내 선호에 가장 잘 맞는지 확신하는 것은 불가능했다.", true), points: 9 },
      { ...lk("CC_2", "내 선호에 가장 잘 맞는 상품 하나를 골라낼 때 확신이 있었다."), points: 9 },
      { ...lk("CC_3", "내 필요를 가장 잘 충족하는 상품을 찾았다고 확신한다."), points: 9 },
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
// Raw NASA-TLX (Hart 1986; 쌍대비교 생략 RTLX) — guardrail (2026-08-24 동결 문서 §5).
// 0~100, 5 간격 21눈금, 기본값 미선택. 수행 문항만 방향이 반대(0=매우 좋음)로 보이지만
// 문서 지시대로 "0=매우 좋음/성공적, 100=매우 나쁨"으로 두어 여섯 문항 모두 높음=부담.
const tlx = (id: string, label: string, minLabel: string, maxLabel: string): MQuestion =>
  ({ id, label, type: "slider", minLabel, maxLabel, required: true });

export const POST_STUDY: MSection[] = [
  {
    id: "nasa_tlx",
    title: "작업 부담 (두 과제 전체)",
    desc: "방금 수행한 두 번의 쇼핑 과제에서 쇼핑 에이전트와 상호작용한 경험 전체에 관한 문항입니다. 설문 작성 과정은 제외하고, 상품을 탐색·비교하여 최종 선택 여부를 판단한 과정만 생각해 주세요. 각 항목을 0에서 100 사이에서 평가해 주세요.",
    questions: [
      tlx("TLX_MENTAL", "과제를 수행하는 데 어느 정도의 정신적, 지각적 활동이 필요했습니까? (생각하기, 결정하기, 기억하기, 보기, 찾기 등) 과제는 쉬웠습니까, 아니면 정신적으로 부담이 컸습니까?", "매우 낮음", "매우 높음"),
      tlx("TLX_PHYSICAL", "과제를 수행하는 데 어느 정도의 신체적 활동이 필요했습니까? (누르기, 움직이기, 입력하고 조작하기 등) 과제는 편안했습니까, 아니면 신체적으로 힘들었습니까?", "매우 낮음", "매우 높음"),
      tlx("TLX_TEMPORAL", "과제나 과제 요소가 진행되는 속도 때문에 어느 정도의 시간 압박을 느꼈습니까? 진행 속도는 느긋했습니까, 아니면 빠르고 촉박했습니까?", "매우 낮음", "매우 높음"),
      tlx("TLX_PERFORMANCE", "과제의 목표를 달성하는 데 본인이 얼마나 성공적이었다고 생각합니까? 그 목표를 달성한 자신의 수행에 얼마나 만족합니까?", "매우 좋음, 성공적임", "매우 나쁨, 성공적이지 않음"),
      tlx("TLX_EFFORT", "자신의 수행 수준에 도달하기 위해 정신적으로, 신체적으로 얼마나 열심히 노력해야 했습니까?", "매우 낮음", "매우 높음"),
      tlx("TLX_FRUSTRATION", "과제를 수행하는 동안 얼마나 불안하고, 낙담하고, 짜증 나고, 스트레스를 받고, 신경이 쓰였습니까?", "매우 낮음", "매우 높음"),
    ],
  },
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
  // 탐색 축소 개방형 (동결 문서 §7) — 검증 척도 아님, 합산 없음, 질적 해석 전용.
  {
    id: "exploration_narrowing",
    title: "탐색 범위에 대한 경험",
    questions: [
      {
        id: "OPEN_NARROWING",
        type: "text",
        label: "에이전트와 대화하는 동안, 에이전트가 제시하거나 강조한 내용 때문에 탐색 범위가 필요 이상으로 좁아졌거나 다른 중요한 기준 또는 상품을 충분히 고려하지 못했다고 느낀 적이 있었습니까? 없다면 '없음'이라고 적고, 있다면 당시 상황과 선택에 미친 영향을 설명해 주세요.",
        placeholder: "없다면 '없음'",
        required: true,
      },
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
// eslint-disable-next-line @typescript-eslint/no-unused-vars
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

/** 리커트(문항별 points 반영)·슬라이더 문항 대상 섹션별 평균. reverse는 (points+1 - v).
 *  슬라이더(RTLX)는 0~100 원값 평균 — 여섯 차원 산술평균이 Raw NASA-TLX다.
 *  구성개념은 각각 보고하며 전체 합산 점수는 만들지 않는다 (측정 계획 §10). */
export function computeSectionScores(
  sections: MSection[],
  answers: Record<string, unknown>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const sec of sections) {
    const vals: number[] = [];
    for (const q of sec.questions) {
      if (q.type !== "likert" && q.type !== "slider") continue;
      const v = Number(answers[q.id]);
      if (!Number.isFinite(v) || (q.type === "likert" && v <= 0) || v < 0) continue;
      if (q.type === "slider") { vals.push(v); continue; }
      const pts = q.points ?? LIKERT_POINTS;
      vals.push(q.reverse ? pts + 1 - v : v);
    }
    if (vals.length) {
      out[sec.id] = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
    }
  }
  return out;
}
