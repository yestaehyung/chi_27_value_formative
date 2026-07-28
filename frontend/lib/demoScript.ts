// 발표용 자동 재생 데모 스크립트 (formative study 발표).
//
// 백엔드를 전혀 호출하지 않는 **고정 시나리오**다. 실제 컴포넌트(MessageBubble ·
// ProductCarousel · SequentialCriteriaConfirm · ConflictUtterance)에 그대로 주입하므로
// 화면은 실제 세션과 동일하고, 재생 결과만 결정론적이다 — 발표 중 LLM 지연·실패가 없다.
//
// 대화 설계(사용자 6발화는 실제 스크립트 그대로):
//   1 세로 모니터        → recommend
//   2 4K로 다시          → recommend (조건 누적)
//   3 몇 인치가 적당?     → answer     (재검색 없이 답변 — 4-action 어휘 시연)
//   4 27인치·심플        → recommend + 기준 확인 (말하지 않은 기준을 추론해 되물음)
//   5 첫 번째 좋은데 비쌈 → recommend (숨은 의도: 예산 상한)
//   6 대기업 중 저렴하게  → 충돌 카드 → 해소 → 재추천 (핵심 기여)

import type { Conflict, Impression, PreferenceChip, Product, Turn } from "@/lib/types";

const T0 = "2026-01-01T00:00:00Z";

// ─────────────────────────────────────────────────────────────────────
// 상품
// ─────────────────────────────────────────────────────────────────────
type Cue = Product["cueSummary"];
const cue = (
  priceCue: Cue["priceCue"],
  trustCue: Cue["trustCue"] = "high",
  popularityCue: Cue["popularityCue"] = "popular",
): Cue => ({ priceCue, trustCue, popularityCue, sellerCue: "trusted", noveltyCue: "common" });

const p = (
  id: string,
  title: string,
  brand: string,
  price: number,
  rating: number,
  reviewCount: number,
  attributes: Product["attributes"],
  description: string,
  c: Cue,
): Product => ({
  id, title, brand, price, rating, reviewCount, attributes, description,
  category: "모니터", deliveryFee: 0, sellerName: `${brand} 공식스토어`, sellerGrade: "빅파워",
  longTermReviewRatio: 0.38, recentSalesCount: 210, cueSummary: c,
});

const PRODUCTS: Record<string, Product> = {
  // 1턴 — 세로 회전(피벗) 지원
  m_pivot_1: p("m_pivot_1", "삼성 S32A600 32인치 QHD 피벗 스탠드", "삼성", 379000, 4.5, 1820,
    { 크기: "32인치", 해상도: "QHD (2560×1440)", 피벗: true, 패널: "VA" },
    "높이·피벗 조절 스탠드를 갖춘 32인치 QHD. 세로 배치가 기본 지원됩니다.", cue("mid")),
  m_pivot_2: p("m_pivot_2", "LG 27QN880 27인치 QHD 에르고 스탠드", "LG", 429000, 4.7, 2410,
    { 크기: "27인치", 해상도: "QHD (2560×1440)", 피벗: true, 패널: "IPS" },
    "클램프형 에르고 스탠드로 세로 전환과 높이 조절이 자유롭습니다.", cue("high")),
  m_pivot_3: p("m_pivot_3", "한성컴퓨터 TFG27Q 27인치 QHD 피벗", "한성컴퓨터", 249000, 4.3, 940,
    { 크기: "27인치", 해상도: "QHD (2560×1440)", 피벗: true, 패널: "IPS" },
    "피벗 스탠드를 갖춘 가성비 QHD 모니터.", cue("low", "medium", "moderate")),

  // 2턴 — 4K
  m_4k_1: p("m_4k_1", "LG 27UP850 27인치 4K IPS USB-C", "LG", 549000, 4.7, 3120,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 피벗: true, USB_C: "90W 충전" },
    "USB-C 한 케이블로 노트북 연결·충전이 되는 4K IPS.", cue("high")),
  m_4k_2: p("m_4k_2", "삼성 U28R550 28인치 4K", "삼성", 389000, 4.4, 2050,
    { 크기: "28인치", 해상도: "4K (3840×2160)", 피벗: true, 패널: "IPS" },
    "28인치 4K 기본기에 충실한 사무용 모니터.", cue("mid")),
  m_4k_3: p("m_4k_3", "벤큐 EW2780U 27인치 4K HDRi", "벤큐", 619000, 4.6, 780,
    { 크기: "27인치", 해상도: "4K (3840×2160)", HDR: "HDRi", 스피커: "2.1채널" },
    "밝기 자동 조절과 내장 스피커를 갖춘 27인치 4K.", cue("very_high", "high", "moderate")),

  // 4턴 — 27인치 + 심플 디자인
  m_simple_1: p("m_simple_1", "LG 27UP650 27인치 4K 무결점 화이트", "LG", 489000, 4.6, 1640,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "화이트", 베젤: "3면 무베젤" },
    "군더더기 없는 화이트 3면 무베젤. 책상 위에서 시각적으로 조용합니다.", cue("high")),
  m_simple_2: p("m_simple_2", "델 S2722QC 27인치 4K USB-C", "델", 529000, 4.7, 2280,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "실버", USB_C: "65W 충전" },
    "은색 미니멀 스탠드에 USB-C 도킹을 겸하는 27인치 4K.", cue("high")),
  m_simple_3: p("m_simple_3", "필립스 27E1N1900AE 27인치 4K", "필립스", 379000, 4.3, 610,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "블랙", 패널: "IPS" },
    "장식 없는 무광 블랙 마감의 27인치 4K.", cue("mid", "medium", "moderate")),

  // 5턴 — 첫 번째(LG 27UP650)와 비슷하되 가격을 낮춘 대안
  m_value_1: p("m_value_1", "필립스 27E1N1900AE 27인치 4K 화이트", "필립스", 359000, 4.3, 610,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "화이트", 베젤: "3면 무베젤" },
    "첫 번째와 같은 화이트·무베젤 계열이면서 13만원 저렴합니다.", cue("mid", "medium", "moderate")),
  m_value_2: p("m_value_2", "한성컴퓨터 ULTRON 2799U 27인치 4K", "한성컴퓨터", 329000, 4.2, 1130,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "블랙", 패널: "IPS" },
    "27인치 4K 최저가대. 스탠드는 기울기 조절만 됩니다.", cue("low", "medium", "moderate")),
  m_value_3: p("m_value_3", "알파스캔 IPS275U 27인치 4K", "알파스캔", 299000, 4.1, 720,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "블랙", 패널: "IPS" },
    "가장 저렴한 27인치 4K. 피벗은 미지원입니다.", cue("very_low", "low", "niche")),

  // 6턴 해소 후 — 대기업 중 가격이 괜찮은 것
  m_brand_1: p("m_brand_1", "삼성 U28R550 28인치 4K", "삼성", 389000, 4.4, 2050,
    { 크기: "28인치", 해상도: "4K (3840×2160)", 피벗: true, 색상: "다크블루" },
    "대기업 4K 중 가장 낮은 가격대. 피벗도 지원합니다.", cue("mid")),
  m_brand_2: p("m_brand_2", "델 S2721QS 27인치 4K", "델", 449000, 4.6, 1980,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 피벗: true, 색상: "실버" },
    "27인치를 유지하면서 델 제품 중 가장 저렴한 4K입니다.", cue("mid")),
  m_brand_3: p("m_brand_3", "LG 27UP650 27인치 4K 무결점 화이트", "LG", 489000, 4.6, 1640,
    { 크기: "27인치", 해상도: "4K (3840×2160)", 색상: "화이트", 베젤: "3면 무베젤" },
    "처음 마음에 들어 하셨던 제품. 참고용으로 함께 둡니다.", cue("high")),
};

// ─────────────────────────────────────────────────────────────────────
// 추천 세트 (턴별 노출 상품 + 추천 이유)
// ─────────────────────────────────────────────────────────────────────
type SetItem = { id: string; reason: string; matched: string[]; weak: string[] };

const SETS: Record<string, SetItem[]> = {
  pivot: [
    { id: "m_pivot_2", reason: "에르고 스탠드라 세로 전환이 가장 수월해요.",
      matched: ["세로(피벗) 지원", "연구실 책상에 클램프 장착 가능"], weak: ["가격대가 조금 높아요"] },
    { id: "m_pivot_1", reason: "32인치라 세로로 세웠을 때 문서가 길게 들어옵니다.",
      matched: ["세로(피벗) 지원", "화면이 큼"], weak: ["책상 깊이가 얕으면 부담될 수 있어요"] },
    { id: "m_pivot_3", reason: "피벗을 갖춘 것 중 가장 저렴한 선택지예요.",
      matched: ["세로(피벗) 지원", "가격 부담 적음"], weak: ["브랜드 인지도는 낮은 편"] },
  ],
  fourk: [
    { id: "m_4k_1", reason: "4K에 피벗까지 되고, USB-C 한 선으로 노트북과 연결됩니다.",
      matched: ["4K 해상도", "세로(피벗) 지원"], weak: ["가격이 가장 높아요"] },
    { id: "m_4k_2", reason: "4K·피벗을 갖추면서 가격이 가장 낮습니다.",
      matched: ["4K 해상도", "세로(피벗) 지원"], weak: ["28인치라 27인치보다 조금 큽니다"] },
    { id: "m_4k_3", reason: "밝기 자동 조절이 있어 오래 봐도 눈이 덜 피로합니다.",
      matched: ["4K 해상도"], weak: ["피벗 미지원", "가격이 높음"] },
  ],
  simple: [
    { id: "m_simple_1", reason: "화이트 3면 무베젤이라 책상에서 가장 눈에 덜 띕니다.",
      matched: ["27인치", "심플한 디자인", "4K 해상도"], weak: ["가격이 중상위권"] },
    { id: "m_simple_2", reason: "실버 미니멀 스탠드에 USB-C 도킹을 겸합니다.",
      matched: ["27인치", "심플한 디자인", "4K 해상도"], weak: ["가격이 가장 높음"] },
    { id: "m_simple_3", reason: "무광 블랙 마감으로 장식 요소가 없습니다.",
      matched: ["27인치", "심플한 디자인", "4K 해상도"], weak: ["스탠드 조절 폭이 좁아요"] },
  ],
  value: [
    { id: "m_value_1", reason: "첫 번째와 같은 화이트·무베젤 계열이면서 13만원 낮습니다.",
      matched: ["심플한 디자인", "27인치", "예산 부담 낮춤"], weak: ["피벗 미지원"] },
    { id: "m_value_2", reason: "27인치 4K 중 가장 낮은 가격대입니다.",
      matched: ["27인치", "4K 해상도", "예산 부담 낮춤"], weak: ["디자인은 평범한 편"] },
    { id: "m_value_3", reason: "가격을 최우선으로 볼 때의 선택지예요.",
      matched: ["27인치", "예산 부담 낮춤"], weak: ["피벗 미지원", "브랜드 인지도 낮음"] },
  ],
  brand: [
    { id: "m_brand_2", reason: "27인치를 지키면서 대기업 제품 중 가장 저렴합니다.",
      matched: ["대기업 브랜드", "27인치", "4K 해상도", "예산 고려"], weak: ["디자인은 무난한 수준"] },
    { id: "m_brand_1", reason: "대기업 4K 전체에서 가장 낮은 가격이에요.",
      matched: ["대기업 브랜드", "4K 해상도", "예산 고려"], weak: ["28인치라 1인치 큽니다"] },
    { id: "m_brand_3", reason: "처음 마음에 들어 하신 제품 — 비교용으로 함께 둡니다.",
      matched: ["대기업 브랜드", "심플한 디자인", "27인치"], weak: ["세 개 중 가장 비쌉니다"] },
  ],
};

export function impressionsFor(setKey: string, turnId: string): Impression[] {
  return (SETS[setKey] ?? []).map((it, i) => ({
    id: `${turnId}_imp${i}`,
    turnId,
    productId: it.id,
    rank: i,
    recommendationReason: it.reason,
    matchedIntentions: it.matched,
    weakIntentions: it.weak,
    product: PRODUCTS[it.id],
    createdAt: T0,
  }));
}

// ─────────────────────────────────────────────────────────────────────
// 기준(칩)
// ─────────────────────────────────────────────────────────────────────
const chip = (
  id: string,
  label: string,
  type: PreferenceChip["type"],
  status: string,
  rationale: string,
  evidenceCount = 1,
): PreferenceChip => ({
  id, label, type, status, displayRationale: rationale, evidenceCount,
  userEditable: true, priority: type === "must_have" ? "high" : "medium",
  confidence: status === "confirmed" ? 1 : 0.55,
});

export const CHIPS = {
  pivot: chip("c_pivot", "세로(피벗) 배치", "must_have", "confirmed",
    "“연구실에서 사용할 세로 모니터”라고 직접 말씀하셨어요."),
  lab: chip("c_lab", "연구실 책상에서 사용", "important", "confirmed",
    "“연구실에서 사용할”이라고 사용 맥락을 밝히셨어요."),
  fourk: chip("c_4k", "4K 해상도", "must_have", "confirmed",
    "“4k 지원되는 모니터로”라고 직접 요청하셨어요."),
  size: chip("c_size", "27인치", "must_have", "confirmed",
    "“그럼 27인치로 하고”라고 확정하셨어요."),
  simple: chip("c_simple", "심플한 디자인", "important", "confirmed",
    "“디자인은 심플했으면 좋겠어”라고 말씀하셨어요."),
  // ── 말하지 않은 기준 (이 연구의 핵심) ──
  multitask: chip("c_multi", "문서를 여러 개 띄워놓고 보는 작업", "uncertain", "inferred",
    "세로 배치 + 4K + 연구실이라는 조합에서 추론했어요. 직접 말씀하신 적은 없습니다.", 3),
  budget: chip("c_budget", "50만원 아래로 맞추고 싶음", "important", "inferred",
    "“가격이 조금 비싼거같아” — 48.9만원 제품을 두고 하신 말에서 추론했어요.", 2),
  brand: chip("c_brand", "대기업 브랜드 우선", "must_have", "confirmed",
    "“dell, lg 처럼 대기업 제품을 우선적으로”라고 말씀하셨어요."),
};

// ─────────────────────────────────────────────────────────────────────
// 충돌 — 예산 vs 대기업 브랜드
// ─────────────────────────────────────────────────────────────────────
export const DEMO_CONFLICT: Conflict = {
  id: "demo_conf_1",
  severity: "direct",
  status: "shown_to_user",
  conflictType: "criteria_tradeoff",
  oldAssumption: "50만원 아래로 맞추고 싶음",
  newSignal: "Dell·LG 같은 대기업 제품을 우선",
  explanationForUser:
    "대기업 27인치 4K는 44만원대부터 시작해요. 아까 “조금 비싸다”고 하신 가격대와 겹치는데, 어느 쪽을 우선할까요?",
  suggestedResolutions: [
    { id: "opt_merge", action: "merge", label: "둘 다 — 대기업 중에서 가장 저렴한 걸로",
      resultingStatePreview: "대기업 브랜드로 좁히되 가격 낮은 순으로 정렬해서 추천할게요." },
    { id: "opt_brand", action: "accept_new", label: "브랜드를 우선할게요",
      resultingStatePreview: "예산 기준은 내리고 대기업 제품 위주로 추천할게요." },
    { id: "opt_price", action: "keep_old", label: "가격을 우선할게요",
      resultingStatePreview: "브랜드는 가리지 않고 27인치 4K 중 저렴한 순으로 추천할게요." },
  ],
  createdAt: T0,
};

// ─────────────────────────────────────────────────────────────────────
// 재생 비트 — 플레이어가 순서대로 적용한다
// ─────────────────────────────────────────────────────────────────────
export type Beat =
  | { t: "user"; text: string; ms: number }
  | { t: "thinking"; ms: number }
  | { t: "agent"; text: string; action: string; set?: string; ms: number }
  | { t: "chips"; add: PreferenceChip[]; ms: number }
  | { t: "confirm"; ms: number }            // 순차 기준 확인 위젯 등장
  | { t: "confirmAnswer"; ms: number }      // 사용자가 '맞아요'
  | { t: "conflict"; ms: number }
  | { t: "resolve"; optionId: string; ms: number }
  | { t: "end"; ms: number };

const C = CHIPS;

export const BEATS: Beat[] = [
  // ── 1턴 ──
  { t: "user", text: "연구실에서 사용할 세로 모니터 하나 사려고. 추천해줘", ms: 900 },
  { t: "thinking", ms: 1400 },
  { t: "agent", action: "recommend", set: "pivot",
    text: "연구실에서 세로로 세워 쓰실 모니터군요. 피벗(세로 회전)이 되는 제품으로 세 가지를 서로 다른 방향에서 골라봤어요. 마음에 드는 쪽에 반응해주시면 기준을 더 좁혀볼게요.", ms: 1600 },
  { t: "chips", add: [C.pivot, C.lab], ms: 1200 },

  // ── 2턴 ──
  { t: "user", text: "4k 지원되는 모니터로 다시 추천해줄래", ms: 1600 },
  { t: "thinking", ms: 1300 },
  { t: "agent", action: "recommend", set: "fourk",
    text: "4K로 좁혀서 다시 골랐어요. 세로 배치 조건은 그대로 유지했습니다.", ms: 1500 },
  { t: "chips", add: [C.fourk], ms: 1100 },

  // ── 3턴 — answer (재검색 없음) ──
  { t: "user", text: "일반적으로 학교에서 쓰는 사무용 책상에서 쓰려면 몇 인치 정도가 적당하지?", ms: 1900 },
  { t: "thinking", ms: 1200 },
  { t: "agent", action: "answer",
    text: "학교 사무용 책상은 깊이가 보통 60~70cm입니다. 이 거리(약 60cm)에서는 27인치가 화면 전체를 눈만 움직여 보기에 편해요. 32인치는 세로로 세우면 위쪽을 올려다보게 돼서, 책상이 얕으면 목이 불편해질 수 있습니다.", ms: 2600 },

  // ── 4턴 — 추천 + 말하지 않은 기준 확인 ──
  { t: "user", text: "그럼 27인치로 하고, 디자인은 심플했으면 좋겠어.", ms: 1700 },
  { t: "thinking", ms: 1400 },
  { t: "agent", action: "recommend", set: "simple",
    text: "27인치 4K 중에서 장식이 적고 베젤이 얇은 쪽으로 골랐어요.", ms: 1500 },
  { t: "chips", add: [C.size, C.simple], ms: 1000 },
  { t: "confirm", ms: 1800 },
  { t: "confirmAnswer", ms: 2400 },

  // ── 5턴 — 숨은 의도(예산) ──
  { t: "user", text: "첫 번째가 마음에 드는데, 가격이 조금 비싼거같아", ms: 1900 },
  { t: "thinking", ms: 1400 },
  { t: "agent", action: "recommend", set: "value",
    text: "첫 번째(LG 27UP650, 48.9만원)의 화이트·무베젤 느낌은 살리면서 가격을 낮춘 쪽으로 다시 골랐어요.", ms: 1700 },
  { t: "chips", add: [C.budget], ms: 1200 },

  // ── 6턴 — 충돌 → 해소 → 재추천 ──
  { t: "user", text: "dell, lg 처럼 대기업 제품을 우선적으로 고려하고 싶은데 그중에서 가격 괜찮은걸로 다시 추천해줘", ms: 2100 },
  { t: "thinking", ms: 1500 },
  { t: "chips", add: [C.brand], ms: 700 },
  { t: "conflict", ms: 2200 },
  { t: "resolve", optionId: "opt_merge", ms: 2600 },
  { t: "end", ms: 1200 },
];

export function makeTurn(
  id: string,
  role: Turn["role"],
  content: string,
  turnIndex: number,
  agentAction?: string,
): Turn {
  return { id, sessionId: "demo", turnIndex, role, content, dialogueActs: [],
           relatedProductIds: [], agentAction, createdAt: T0 };
}

/** 해소 직후 에이전트 발화 + 재추천 세트 */
export const RESOLUTION = {
  message: "알겠어요. 대기업 브랜드로 좁히되, 그 안에서 가격이 낮은 순으로 다시 골라볼게요.",
  followUp: "Dell·LG·삼성 중에서 27인치 4K를 가격 순으로 정리했어요. 44.9만원부터 시작합니다.",
  set: "brand",
};
