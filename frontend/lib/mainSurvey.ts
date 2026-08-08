// 메인 스터디(본실험) 설문 정의 — 5개 도구.
//
// FS1 사전 설문(`survey.ts`)과는 별개다. FS1은 탐색적 프로파일링(TCV 가치·쇼핑 동기)이
// 목적이었고, 본실험은 3조건 between-subjects × 3카테고리 within-subjects 설계에서
// 조건 간 차이를 재는 것이 목적이라 문항 구성이 다르다.
//
// 시점별 5개 도구:
//   1. PRE_STUDY      연구 시작 전 · 참가자 1회      → Participant.survey
//   2. PRE_TASK       각 쇼핑 과제 직전 · 세션마다   → Session.meta.preTaskSurvey
//   3. POST_TASK      각 쇼핑 과제 직후 · 세션마다   → Session.meta.postSurvey
//   4. POST_STUDY     전체 과제 종료 후 · 참가자 1회 → Participant.survey.postStudy
//   5. CRITERION_CHECK 추론된 기준별 · 과제마다 3–5개 → criterion_validations 테이블
//
// 핵심 설계: PRE_TASK의 "구매 기준 명확성" 3문항과 POST_TASK의 첫 3문항은 **동일 문항**이다.
// 과제 전후 차이(Δ)가 조건 간 주요 비교치이므로, 같은 문항 텍스트를 한 곳(CRITERIA_CLARITY)에서
// 정의해 양쪽이 공유한다 — 문구가 갈라지면 차이값이 오염된다.

export type MQType = "single" | "likert";

export type MQuestion = {
  id: string;
  label: string;
  type: MQType;
  options?: string[]; // single
  /** 리커트 양 끝 라벨. 생략 시 기본(전혀 그렇지 않다 ~ 매우 그렇다) */
  minLabel?: string;
  maxLabel?: string;
  /** 구인 평균 계산 시 (8 - v)로 뒤집는다. NASA-TLX 성공도 전용. */
  reverse?: boolean;
  /** 미응답이면 제출 불가 (참여 동의 문항) */
  required?: boolean;
  /** 이 값을 고르면 연구 참여 제외 */
  excludeIf?: string;
};

export type MSection = {
  id: string;
  title: string;
  desc?: string;
  questions: MQuestion[];
};

export const LIKERT_POINTS = 7;
export const LIKERT_MIN = "전혀 그렇지 않다";
export const LIKERT_MAX = "매우 그렇다";

/** 7점 리커트 (기본 앵커) */
const lk = (id: string, label: string): MQuestion => ({ id, label, type: "likert" });
/** 7점 리커트 (앵커 지정) */
const lkA = (id: string, label: string, minLabel: string, maxLabel: string, reverse = false): MQuestion =>
  ({ id, label, type: "likert", minLabel, maxLabel, reverse });
/** 객관식 */
const sg = (id: string, label: string, options: string[]): MQuestion =>
  ({ id, label, type: "single", options });
/** 참여 동의/자격 — 미응답이면 제출 불가, `no`를 고르면 참여 제외 */
const consent = (id: string, label: string): MQuestion =>
  ({ id, label, type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" });

// ─────────────────────────────────────────────────────────────────────
// 공유 문항: 구매 기준 명확성 (과제 직전·직후 동일 문항, Δ 측정용)
// ─────────────────────────────────────────────────────────────────────
const CRITERIA_CLARITY: { key: string; label: string }[] = [
  { key: "CLARITY_1", label: "이 상품을 선택할 때 중요하게 고려해야 할 기준이 무엇인지 명확하다." },
  { key: "CLARITY_2", label: "여러 구매 기준 중 무엇을 더 우선해야 하는지 명확하다." },
  { key: "CLARITY_3", label: "반드시 충족해야 할 조건과 타협 가능한 조건을 구분할 수 있다." },
];

const clarityQuestions = (prefix: "TPRE" | "TPOST"): MQuestion[] =>
  CRITERIA_CLARITY.map((c) => lk(`${prefix}_${c.key}`, c.label));

// ─────────────────────────────────────────────────────────────────────
// 1. 연구 시작 전 사전 설문 (참가자 1회)
// ─────────────────────────────────────────────────────────────────────
export const PRE_STUDY_INTRO =
  "본 설문은 대화형 쇼핑 에이전트 연구의 사전 설문입니다. 정답은 없으며, 평소 경험에 " +
  "가장 가까운 답을 선택해 주세요. 소요 시간은 약 3분입니다.";

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
    id: "shopping",
    title: "온라인 쇼핑 경험",
    questions: [
      sg("PRE_1", "온라인 쇼핑을 얼마나 자주 하나요?", [
        "거의 하지 않음", "한 달에 1회 미만", "한 달에 1–2회",
        "일주일에 1회 정도", "일주일에 여러 번", "거의 매일",
      ]),
    ],
  },
  {
    id: "llm",
    title: "LLM 사용 경험",
    questions: [
      sg("PRE_2", "ChatGPT, Claude, Gemini 등의 AI 챗봇을 얼마나 자주 사용하나요?", [
        "사용해 본 적 없음", "몇 번 사용해 봄", "한 달에 1–2회",
        "일주일에 1–2회", "일주일에 여러 번", "거의 매일",
      ]),
      lk("PRE_3", "AI와 여러 번 대화하면서 요청을 구체화하는 데 익숙하다."),
      lk("PRE_4", "AI가 내 요청을 잘못 이해했을 때 이를 수정하는 데 익숙하다."),
    ],
  },
  {
    id: "ai_rec",
    title: "AI 상품 추천 경험",
    questions: [
      sg("PRE_5", "AI에게 상품 추천이나 구매 조언을 받아 본 적이 있나요?", [
        "없다", "몇 번 있다", "자주 있다",
      ]),
      sg("PRE_6", "AI의 상품 추천을 실제 상품 비교나 구매 결정에 활용한 적이 있나요?", [
        "없다", "상품 비교에 참고한 적이 있다", "실제 구매 결정에 활용한 적이 있다",
      ]),
    ],
  },
  {
    id: "agent_knowledge",
    title: "AI 에이전트에 대한 지식",
    questions: [
      lk("PRE_7", "AI 에이전트가 대화를 바탕으로 사용자의 선호를 추론하고 갱신할 수 있음을 알고 있다."),
      lk("PRE_8", "AI 에이전트가 사용자의 의도나 상품 정보를 잘못 해석할 수 있음을 알고 있다."),
    ],
  },
  {
    id: "prior_trust",
    title: "AI 상품 추천에 대한 사전 신뢰",
    questions: [
      lk("PRE_9", "AI 상품 추천은 구매 결정에 유용한 도움을 줄 수 있다고 생각한다."),
      lk("PRE_10", "중요한 구매에서는 AI 추천을 다른 정보와 비교하거나 확인할 필요가 있다고 생각한다."),
    ],
  },
];

/** 미응답이면 제출 불가한 문항 (참여 동의) — 정의에서 파생하므로 따로 관리하지 않는다 */
export const PRE_STUDY_REQUIRED_IDS = allQuestions(PRE_STUDY)
  .filter((q) => q.required)
  .map((q) => q.id);

/** 사전 설문 파생 점수 — 리커트 섹션(llm/agent_knowledge/prior_trust)만 평균이 의미 있다 */
export function computePreStudyProfile(answers: Record<string, unknown>): Record<string, number> {
  return computeSectionScores(PRE_STUDY, answers);
}

// ─────────────────────────────────────────────────────────────────────
// 2. 각 쇼핑 과제 직전 설문 (세션마다 · [상품군] 치환)
// ─────────────────────────────────────────────────────────────────────
export const PRE_TASK: MSection[] = [
  {
    id: "domain_knowledge",
    title: "상품군별 지식과 경험",
    questions: [
      // 카테고리 이름을 따옴표로 감싼다 — "나는 "모니터"에 대해 잘 알고 있다"처럼
      // 무엇에 대한 문항인지 한눈에 잡히게 (2026-08-08).
      lk("TPRE_K1", '나는 "{category}"에 대해 잘 알고 있다.'),
      lk("TPRE_K2", '나는 "{category}"의 상품 간 차이를 평가할 수 있다.'),
      sg("TPRE_E1", '이전에 "{category}"을(를) 직접 구매한 경험이 있나요?', [
        "없다", "1회 있다", "2회 이상 있다",
      ]),
      sg("TPRE_E2", '현재 또는 과거에 "{category}"을(를) 사용한 경험이 있나요?', [
        "없다", "1년 미만 사용한 경험이 있다", "1년 이상 사용한 경험이 있다",
      ]),
    ],
  },
  {
    id: "criteria_clarity",
    title: "구매 기준 명확성",
    questions: clarityQuestions("TPRE"),
  },
];

// ─────────────────────────────────────────────────────────────────────
// 3. 각 쇼핑 과제 직후 설문 (세션마다)
// ─────────────────────────────────────────────────────────────────────
export const POST_TASK: MSection[] = [
  {
    id: "criteria_clarity",
    title: "구매 기준 명확성",
    desc: "과제 직전과 같은 문항입니다. 지금 시점의 생각으로 답해 주세요.",
    questions: clarityQuestions("TPOST"),
  },
  {
    id: "intent_alignment",
    title: "에이전트의 의도 이해 정합성",
    questions: [
      lk("TPOST_A1", "에이전트는 내가 중요하게 생각한 구매 기준을 잘 이해했다."),
      lk("TPOST_A2", "에이전트는 내가 특정 기준을 중요하게 생각한 이유와 상황을 잘 이해했다."),
      lk("TPOST_A3", "에이전트가 반영한 기준의 우선순위는 내 생각과 일치했다."),
    ],
  },
  {
    id: "control",
    title: "사용자 통제와 수정 가능성",
    questions: [
      lk("TPOST_U1", "에이전트가 나를 잘못 이해했을 때 이를 바로잡을 수 있었다."),
      lk("TPOST_U2", "추천에 사용되는 구매 기준을 내가 원하는 방향으로 조정할 수 있었다."),
    ],
  },
  {
    id: "outcome",
    title: "추천 및 의사결정 결과",
    questions: [
      lk("TPOST_O1", "추천 결과는 현재 구매 목적과 기준에 적합했다."),
      lk("TPOST_O2", "추천 결과에 전반적으로 만족한다."),
      lk("TPOST_O3", "이 결과를 바탕으로 상품을 선택할 자신이 있다."),
    ],
  },
  {
    id: "trust",
    title: "사용한 에이전트에 대한 신뢰",
    questions: [
      lk("TPOST_T1", "이 에이전트의 추천과 해석을 신뢰할 수 있었다."),
      lk("TPOST_T2", "이 에이전트는 자신의 한계나 불확실성을 적절히 드러냈다."),
    ],
  },
  {
    id: "tlx",
    title: "과제 부담 (NASA-TLX)",
    desc: "이번 과제를 수행하면서 느낀 정도를 표시해 주세요.",
    questions: [
      lkA("TPOST_TLX_MENTAL", "이 과제는 정신적으로 얼마나 부담스러웠나요?", "매우 낮음", "매우 높음"),
      lkA("TPOST_TLX_PHYSICAL", "이 과제는 신체적으로 얼마나 부담스러웠나요?", "매우 낮음", "매우 높음"),
      lkA("TPOST_TLX_TEMPORAL", "이 과제를 수행하는 동안 시간적 압박을 얼마나 느꼈나요?", "매우 낮음", "매우 높음"),
      // 성공도만 방향이 반대다 — 높을수록 부담이 '낮다'. 종합 점수에서 역채점.
      lkA("TPOST_TLX_PERFORMANCE", "이 과제를 얼마나 성공적으로 수행했다고 생각하나요?",
        "전혀 성공적이지 않음", "매우 성공적임", true),
      lkA("TPOST_TLX_EFFORT", "이 과제를 수행하기 위해 얼마나 많은 노력을 들였나요?", "매우 낮음", "매우 높음"),
      lkA("TPOST_TLX_FRUSTRATION", "이 과제를 수행하는 동안 얼마나 좌절하거나 불편했나요?", "매우 낮음", "매우 높음"),
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────
// 4. 전체 과제 종료 후 설문 (참가자 1회)
// ─────────────────────────────────────────────────────────────────────
export const POST_STUDY: MSection[] = [
  {
    // 조건 중립 — 세 조건 모두에게 묻는다. 나머지 세 섹션은 전부 '기준을 화면에서 봤다'를
    // 전제하므로 baseline1·baseline2에서는 필터링돼 사라진다. 그러면 조건을 가로지르는
    // 종료 측정치가 하나도 남지 않아 between-subjects 비교 자체가 불가능해진다.
    // 이 섹션이 그 공통 종속변인이다.
    id: "overall",
    title: "전반적 경험",
    questions: [
      lk("END_O1", "이 에이전트의 추천은 전반적으로 내 마음에 들었다."),
      lk("END_O2", "이 에이전트는 내가 무엇을 원하는지 잘 파악했다."),
      lk("END_O3", "이 에이전트를 신뢰할 수 있다고 느꼈다."),
      lk("END_O4", "실제 쇼핑에서도 이런 에이전트를 사용하고 싶다."),
    ],
  },
  {
    id: "interpretability",
    title: "해석의 이해 가능성",
    questions: [
      lk("END_I1", "에이전트가 현재 어떤 구매 기준을 고려하고 있는지 쉽게 이해할 수 있었다."),
      lk("END_I2", "에이전트가 각 기준을 어느 정도 중요하게 보고 있는지 쉽게 파악할 수 있었다."),
      lk("END_I3", "제시된 구매 기준의 표현과 정보량은 이해하기에 적절했다."),
    ],
  },
  {
    id: "evidence",
    title: "근거의 타당성과 추적 가능성",
    questions: [
      lk("END_V1", "각 구매 기준이 어떤 발화나 행동에서 추론되었는지 확인할 수 있었다."),
      lk("END_V2", "제시된 근거는 해당 구매 기준을 적절히 뒷받침했다."),
      lk("END_V3", "근거를 보고 에이전트의 해석이 맞는지 판단할 수 있었다."),
    ],
  },
  {
    id: "edit_usability",
    title: "수정 인터페이스 사용성",
    questions: [
      lk("END_E1", "잘못 추론된 구매 기준을 쉽게 수정하거나 삭제할 수 있었다."),
      lk("END_E2", "구매 기준의 우선순위를 쉽게 조정할 수 있었다."),
      lk("END_E3", "내가 수정한 내용이 이후 추천에 반영되었음을 확인할 수 있었다."),
    ],
  },
];

// 조건별 문항 필터 — 없는 기능의 사용성을 물으면 응답 자체가 무의미하다.
// (통제감 문항 TPOST_U1/U2는 여기서 빼지 않는다: 그건 종속변인이라 baseline에서
//  낮게 나오는 것이 결과다. "없어서 못 물음"과 "없어서 낮음"은 다르다.)
export type StudyCondition = "baseline1" | "baseline2" | "ours";

/** 의도 추론을 돌리는가. baseline1은 돌지 않으므로 '기준별 검증'(⑤)을 물을 수 없다. */
export const INFERS_INTENTION: Record<StudyCondition, boolean> = {
  baseline1: false,
  baseline2: true,
  ours: true,
};
/** 추론한 기준을 화면에 보여주는가 (백엔드 app/core/conditions.py와 짝) */
export const SHOWS_CRITERIA: Record<StudyCondition, boolean> = {
  baseline1: false,
  baseline2: false,
  ours: true,
};
/** 기준을 확인·수정할 수 있는가 */
export const ALLOWS_CORRECTION: Record<StudyCondition, boolean> = {
  baseline1: false,
  baseline2: false,
  ours: true,
};

/**
 * 전체 종료 설문에서 이 조건에 물을 수 있는 섹션만 남긴다.
 *  - 기준을 안 보여준 조건(baseline) → '해석 이해가능성'·'근거 추적' 해당 없음
 *  - 수정 불가 조건 → '수정 인터페이스 사용성' 해당 없음
 * 남는 섹션이 없으면 빈 배열 — 호출부가 설문 자체를 건너뛴다.
 */
export function postStudySectionsFor(condition: StudyCondition | null | undefined): MSection[] {
  const c = (condition ?? "ours") as StudyCondition;
  const shows = SHOWS_CRITERIA[c] ?? true;
  const edits = ALLOWS_CORRECTION[c] ?? true;
  return POST_STUDY.filter((s) => {
    if (s.id === "overall") return true; // 조건 중립 — 언제나 묻는다
    if (s.id === "edit_usability") return edits;
    return shows; // interpretability / evidence
  });
}

// ─────────────────────────────────────────────────────────────────────
// 5. 추론된 구매 기준별 직접 검증 (과제마다 주요 기준 3–5개)
// ─────────────────────────────────────────────────────────────────────
/** 한 기준당 묻는 4문항. {label}은 기준 라벨로 치환된다. */
export const CRITERION_CHECK: MQuestion[] = [
  sg("CRIT_MATCH", "이 구매 기준은 실제 내 생각과 일치합니까?", [
    "일치한다", "부분적으로 일치한다", "일치하지 않는다",
  ]),
  lkA("CRIT_IMPORTANCE", "이 기준은 실제 구매 결정에서 얼마나 중요했습니까?",
    "전혀 중요하지 않았다", "매우 중요했다"),
  sg("CRIT_EVIDENCE", "제시된 발화·선택·거절 근거가 이 기준을 뒷받침합니까?", [
    "뒷받침한다", "부분적으로 뒷받침한다", "뒷받침하지 않는다",
  ]),
  sg("CRIT_FORMATION", "이 기준은 언제 형성되었습니까?", [
    "처음부터 가지고 있었지만 대화에서 직접 표현하지 않았다",
    "원래 가지고 있었지만 대화 중 더 명확해졌다",
    "상품 탐색과 대화 중 새롭게 형성되었다",
  ]),
];

/** 검증 대상으로 제시할 기준 개수 상한 (설문 §5: 주요 기준 3–5개) */
export const CRITERION_CHECK_MAX = 5;
export const CRITERION_CHECK_MIN = 3;

// ─────────────────────────────────────────────────────────────────────
// 헬퍼
// ─────────────────────────────────────────────────────────────────────

/** {category} / {label} 같은 자리표시자를 치환한 섹션 사본을 만든다. */
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

/** 리커트 문항만 대상으로 섹션별 평균. reverse 문항은 (8 - v)로 뒤집는다. */
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

/**
 * 과제 전후 '구매 기준 명확성' 변화량. 본실험의 핵심 종속변인 —
 * 조건(Baseline1/2/Ours) 간 이 Δ를 비교한다.
 * pre/post 응답을 각각 받아 (post 평균 − pre 평균)을 낸다.
 */
export function clarityDelta(
  preAnswers: Record<string, unknown>,
  postAnswers: Record<string, unknown>,
): { pre: number | null; post: number | null; delta: number | null } {
  const avg = (prefix: "TPRE" | "TPOST", src: Record<string, unknown>) => {
    const vals = CRITERIA_CLARITY
      .map((c) => Number(src[`${prefix}_${c.key}`]))
      .filter((v) => Number.isFinite(v) && v > 0);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  const pre = avg("TPRE", preAnswers);
  const post = avg("TPOST", postAnswers);
  return {
    pre: pre === null ? null : Math.round(pre * 100) / 100,
    post: post === null ? null : Math.round(post * 100) / 100,
    delta: pre === null || post === null ? null : Math.round((post - pre) * 100) / 100,
  };
}

/** NASA-TLX 종합 (6문항 평균, 성공도 역채점). 높을수록 부담이 크다. */
export function tlxScore(answers: Record<string, unknown>): number | null {
  const tlx = POST_TASK.find((s) => s.id === "tlx");
  if (!tlx) return null;
  const vals = tlx.questions
    .map((q) => {
      const v = Number(answers[q.id]);
      if (!Number.isFinite(v) || v <= 0) return null;
      return q.reverse ? LIKERT_POINTS + 1 - v : v;
    })
    .filter((v): v is number => v !== null);
  if (!vals.length) return null;
  return Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
}
