// FS1 사전 설문 정의 (formative_study_pre_survey.md 기반).
// 선언형 — survey 페이지가 이 데이터를 렌더한다. 7점 리커트 + 객관식 + 주관식.

export type QType = "single" | "multi" | "likert" | "text" | "textlong";

export type SurveyQuestion = {
  id: string;
  label: string;
  type: QType;
  options?: string[]; // single / multi
  placeholder?: string; // text / textlong
  required?: boolean;
  excludeIf?: string; // 이 값 선택 시 연구 참여 제외
};

export type SurveySection = {
  id: string;
  title: string;
  desc?: string;
  questions: SurveyQuestion[];
};

export const LIKERT_MIN = "전혀 그렇지 않다";
export const LIKERT_MID = "보통이다";
export const LIKERT_MAX = "매우 그렇다";

export const SURVEY_INTRO =
  "본 설문은 대화형 쇼핑 에이전트가 사용자의 구매 기준과 숨은 의도를 어떻게 이해하는지 알아보기 위한 사전 설문입니다. " +
  "정답은 없으며, 평소 쇼핑 방식에 가장 가까운 답을 선택해 주세요. 소요 시간은 약 5분 - 8분 입니다.";

const lk = (id: string, label: string): SurveyQuestion => ({ id, label, type: "likert" });

export const SURVEY: SurveySection[] = [
  {
    id: "A",
    title: "A. 참여 기준 및 동의",
    desc: "연구 참여 가능 여부를 확인합니다.",
    questions: [
      { id: "A1_1", label: "만 19세 이상인가요?", type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" },
      { id: "A1_2", label: "최근 3개월 이내 온라인 쇼핑을 한 적이 있나요?", type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" },
      { id: "A1_4", label: "연구 중 본인의 쇼핑 경험을 이야기하고, 쇼핑 에이전트와 대화하는 과제에 참여할 의향이 있나요?", type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" },
      { id: "A1_5", label: "대화 로그, 클릭/선택/거절 행동, 인터뷰 내용이 연구 목적으로 기록될 수 있음에 동의하나요?", type: "single", options: ["예", "아니오"], required: true, excludeIf: "아니오" },
    ],
  },
  {
    id: "B",
    title: "B. 온라인 쇼핑 행동",
    questions: [
      { id: "B1_1", label: "온라인 쇼핑을 얼마나 자주 하나요?", type: "single", options: ["거의 하지 않음", "한 달에 1회 미만", "한 달에 1–2회", "일주일에 1회 정도", "일주일에 여러 번", "거의 매일"] },
      { id: "B1_2", label: "최근 3개월 동안 온라인에서 구매한 상품군을 모두 선택해 주세요.", type: "multi", options: ["패션/의류", "패션잡화/가방/신발", "화장품/미용", "디지털/가전", "생활/건강", "가구/인테리어", "식품", "스포츠/레저", "출산/육아", "도서/문구", "선물용 상품", "기타"] },
      // B2_2~B2_8은 2026-07-03 설문 축소로 제거 — D/E와 이중 측정이었다
      // (B2_7≈D3_1, B2_8≈D4_2·E2_2, B2_2≈D3_2, B2_3≈D1_2, B2_6≈D2_3;
      //  B2_1·B2_4·B2_5는 같은 숙고 성향의 3중 측정 → 대표 1문항만 유지).
      lk("B2_1", "나는 상품을 구매하기 전에 여러 후보를 비교하는 편이다."),
    ],
  },
  {
    id: "C",
    title: "C. 최근 고민 구매 경험",
    desc: "회상 인터뷰와 에이전트 과제에 사용할 경험을 찾기 위한 섹션입니다.",
    questions: [
      { id: "C1_1", label: "최근 6개월 이내, 구매 전 오래 고민했던 상품이 있었나요?", type: "single", options: ["예", "아니오", "구매하지는 않았지만 오래 고민한 상품은 있다"] },
      { id: "C1_2", label: "그 상품은 무엇인가요?", type: "text", placeholder: "예: 러닝화, 노트북, 친구 생일선물, 여행용 가방, 공기청정기" },
      { id: "C1_2b", label: "그 구매는 누구를 위한 것이었나요?", type: "single", options: ["나 자신", "가족", "친구/지인", "연인", "직장/학교 관련 대상", "기타"] },
      { id: "C1_3", label: "해당 상품을 최종적으로 구매했나요?", type: "single", options: ["구매했다", "구매하지 않았다", "아직 고민 중이다", "다른 상품으로 대체했다"] },
      { id: "C1_4", label: "그 쇼핑 경험은 아래 중 어디에 해당하나요? 모두 선택해 주세요.", type: "multi", options: ["처음 사보는 제품군이라 기준을 잘 몰랐다", "선물용/타인용 구매였다", "여행/출장/운동/이사/업무 등 특정 상황을 위한 구매였다", "가격이 높거나 오래 쓸 제품이라 신중하게 고민했다", "디자인, 스타일, 취향, 이미지가 중요했다", "예산이나 가성비가 중요했다", "착용감, 건강, 안전, 피부/신체 조건이 중요했다", "기존 제품의 고장/불만 때문에 교체/업그레이드", "특정 브랜드나 모델을 염두에 두고 있었다"] },
      { id: "C1_5", label: "처음 검색하거나 AI/검색창에 물어본다면 어떻게 입력했을 것 같나요?", type: "textlong", placeholder: "예: 운동 좋아하는 친구에게 줄 스마트워치 추천해줘" },
      { id: "C1_6", label: "처음부터 분명하게 알고 있던 조건은 무엇이었나요?", type: "textlong", placeholder: "예: 20만원 이하, 검은색, 가벼운 것, 선물용" },
      // C1_7(생각 달라진 점)·C1_9(최종 선택 이유)는 2026-07-03 제거 — 회상 인터뷰에서
      // 구두로 수집하는 내용과 중복(타이핑 부담만 큼). C1_8은 chosen-rejected 이론 신호라 유지.
      { id: "C1_8", label: "마음에 들었지만 결국 선택하지 않은 후보가 있었나요? 왜 선택하지 않았나요?", type: "textlong" },
      { id: "C1_10", label: "이 쇼핑 경험을 연구 중 인터뷰와 에이전트 과제에서 다시 이야기해도 괜찮나요?", type: "single", options: ["예", "아니오", "민감한 내용만 제외하면 가능"] },
    ],
  },
  {
    id: "D",
    title: "D. 소비 가치 성향",
    desc: "전반적인 구매 가치 성향을 파악합니다. (1–7점)",
    questions: [
      lk("D1_1", "나는 상품을 고를 때 성능이나 기능을 가장 먼저 확인한다."),
      lk("D1_2", "나는 가격 대비 효용이 좋은 상품을 선호한다."),
      lk("D1_3", "나는 오래 쓸 수 있는지, 내구성이 좋은지를 중요하게 본다."),
      lk("D2_1", "내가 사용하는 상품이 다른 사람에게 어떻게 보일지 신경 쓰는 편이다."),
      lk("D2_2", "선물용 상품을 고를 때 너무 성의 없어 보이지 않는지가 중요하다."),
      lk("D2_3", "유행하거나 사람들이 많이 쓰는 상품인지가 선택에 영향을 줄 때가 있다."),
      lk("D3_1", "구매 후 후회하지 않을 것 같은 상품을 고르는 것이 중요하다."),
      lk("D3_2", "리뷰나 보증 정보가 충분해야 안심하고 구매할 수 있다."),
      lk("D3_3", "상품을 고를 때 나에게 주는 만족감이나 기분도 중요하다."),
      lk("D4_1", "구매 전에 다양한 선택지를 알아보는 과정이 흥미롭다."),
      lk("D4_2", "새로운 브랜드나 새로운 제품을 발견하는 것을 좋아한다."),
      lk("D4_3", "상품 간 차이를 이해하고 나서 결정하고 싶다."),
      lk("D5_1", "같은 상품이라도 언제, 어디서, 누구를 위해 쓰는지에 따라 선택 기준이 달라진다."),
      lk("D5_2", "특정 상황에 딱 맞는 상품인지가 구매 결정에 중요하다."),
      lk("D5_3", "선물·여행·업무·운동처럼 쓸 상황이 정해져 있으면 그 상황을 가장 먼저 고려한다."),
    ],
  },
  {
    id: "E",
    title: "E. 쇼핑 동기 성향",
    desc: "쇼핑을 목적 달성 중심으로 하는지, 탐색/즐거움 중심으로 하는지 파악합니다. (1–7점)",
    questions: [
      lk("E1_1", "나는 쇼핑할 때 필요한 상품을 빠르고 효율적으로 찾고 싶다."),
      lk("E1_2", "쇼핑에서 가장 중요한 것은 목적에 맞는 상품을 정확히 사는 것이다."),
      lk("E1_3", "너무 많은 상품을 보는 것보다 조건에 맞는 후보를 좁혀주는 것이 좋다."),
      lk("E1_4", "추천 시스템이 내 조건에 맞는 상품을 정리해주면 도움이 된다."),
      lk("E1_5", "구매 결정을 빨리 내릴 수 있으면 쇼핑 경험이 좋아진다."),
      lk("E1_6", "나는 필요한 정보가 충분하면 더 탐색하지 않고 결정하는 편이다."),
      lk("E2_1", "나는 꼭 사지 않더라도 상품을 구경하는 과정 자체를 즐긴다."),
      lk("E2_2", "예상하지 못한 좋은 상품을 발견하면 즐겁다."),
      lk("E2_3", "쇼핑은 나에게 기분전환이나 자기보상의 의미가 있다."),
      lk("E2_4", "나는 여러 상품을 둘러보면서 내 취향을 알아가는 과정이 좋다."),
      lk("E2_5", "평소 몰랐던 새로운 스타일이나 브랜드를 추천받는 것이 좋다."),
      lk("E2_6", "쇼핑할 때 너무 빨리 결론을 내기보다 탐색할 여지가 있으면 좋다."),
    ],
  },
  {
    id: "F",
    title: "F. AI/쇼핑 에이전트 경험 및 기대",
    questions: [
      { id: "F1_1", label: "ChatGPT, Claude, Gemini 등 AI 챗봇을 얼마나 자주 사용하나요?", type: "single", options: ["사용해본 적 없음", "몇 번 사용해봄", "한 달에 1–2회", "일주일에 1–2회", "거의 매일"] },
      { id: "F1_2", label: "AI에게 상품 추천이나 구매 조언을 받아본 적이 있나요?", type: "single", options: ["예, 자주 있다", "예, 몇 번 있다", "아니오, 없다"] },
      // F 대폭 축소 (2026-07-03): F1_3(쇼핑몰 추천 참고≈F1_2), F2_1(일반론 신뢰),
      // F2_2(설명 도움), F2_3(숨은 부분 고려), F2_8(질문으로 기준 정리),
      // F2_9(단정적 표현 불편), F2_10(기준 정리 도움) 제거 — 기대 문항은 태도 표명일 뿐
      // 행동 관찰(FS1 본과제·인터뷰)이 더 정확히 답한다. CorrectabilityNeed 구인 2문항 +
      // AI 경험 공변인 2문항만 유지.
      lk("F2_4", "AI가 나를 잘못 이해했을 때 직접 수정할 수 있어야 한다."),
      lk("F2_5", "AI가 나를 어떻게 이해하고 있는지 확인할 수 있으면 좋겠다."),
    ],
  },
];

// 파생 점수 그룹 (설문 문서 §3) — 인터뷰 probe 준비용 (정량 분석 아님)
const SCORING: { key: string; items: string[] }[] = [
  { key: "Functional", items: ["D1_1", "D1_2", "D1_3"] },
  { key: "Social", items: ["D2_1", "D2_2", "D2_3"] },
  { key: "Emotional", items: ["D3_1", "D3_2", "D3_3"] },
  { key: "Epistemic", items: ["D4_1", "D4_2", "D4_3"] },
  { key: "Conditional", items: ["D5_1", "D5_2", "D5_3"] },
  { key: "Utilitarian", items: ["E1_1", "E1_2", "E1_3", "E1_4", "E1_5", "E1_6"] },
  { key: "Hedonic", items: ["E2_1", "E2_2", "E2_3", "E2_4", "E2_5", "E2_6"] },
  // F2_6(확신 표시)·F2_7(저장 우려/PrivacyConcern)은 2026-07-03 설문 축소로 제거 —
  // CorrectabilityNeed는 남은 2문항 평균 (computeProfile이 답한 항목만 평균하므로
  // 과거 응답자 프로필과도 호환).
  { key: "CorrectabilityNeed", items: ["F2_4", "F2_5"] },
];

export function computeProfile(answers: Record<string, unknown>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const g of SCORING) {
    const vals = g.items
      .map((id) => Number(answers[id]))
      .filter((v) => Number.isFinite(v) && v > 0);
    if (vals.length) out[g.key] = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
  }
  return out;
}

// 필수(참여기준/동의) 문항 — 미응답이면 제출 불가, excludeIf면 참여 제외
export const REQUIRED_IDS = SURVEY.flatMap((s) => s.questions.filter((q) => q.required).map((q) => q.id));
