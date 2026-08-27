export type StudyLocale = "ko" | "en";

export const STUDY_LOCALE: StudyLocale =
  process.env.NEXT_PUBLIC_STUDY_LOCALE === "en" ? "en" : "ko";

// ours-v2 탐색 파일럿 플래그 (2026-08-27) — 칩 온보딩 안내·종료 전 확신 질문·
// 비교형 선택 이유 문구를 켠다. 본실험 비교군과 절대 섞이지 않도록 백엔드
// VC_UI_VARIANT(세션 meta.uiVariant 도장)와 반드시 함께 켜고 함께 끈다.
export const OURS_V2 = process.env.NEXT_PUBLIC_OURS_V2 === "1";

// ours-v3 (2026-08-27): 추천 전 칩 확인 게이트 + 추론 가설 칩 시각 구분. 백엔드
// VC_UI_VARIANT=ours-v3와 반드시 짝으로 — 게이트 턴(agentAction=confirm_chips)은
// 백엔드가 만들고, 프론트는 '추천 보기' 버튼과 가설 배지만 담당한다.
export const OURS_V3 = process.env.NEXT_PUBLIC_OURS_V3 === "1";

export const IS_ENGLISH_STUDY = STUDY_LOCALE === "en";

/** Build-time locale selector for the separately deployed study frontend. */
export function tr<T>(ko: T, en: T): T {
  return IS_ENGLISH_STUDY ? en : ko;
}

export const CATEGORY_EN: Record<string, string> = {
  "블루투스 스피커": "Bluetooth Speakers",
  "티셔츠": "T-shirts",
  "책상": "Desks",
  "데스크체어": "Office Chairs",
  "노트북": "Laptops",
  "청바지": "Jeans",
  "팬츠·바지": "Pants",
  "후드·맨투맨": "Hoodies & Sweatshirts",
  "니트·가디건": "Sweaters & Cardigans",
  "셔츠·블라우스": "Shirts & Blouses",
  "이어폰": "Earphones & Earbuds",
  "헤드폰": "Headphones",
  "키보드·마우스": "Keyboards & Mice",
  "모니터": "Monitors",
  "스마트워치": "Smartwatches",
  "커피테이블": "Coffee Tables",
  "책장": "Bookcases",
};

const CATEGORY_BLURB_EN: Record<string, string> = {
  "집·야외에서 쓸 무선 스피커": "Wireless speakers for indoor or outdoor use",
  "일상에서 입을 티셔츠": "T-shirts for everyday wear",
  "작업용 책상": "Desks for work or study",
  "오래 앉아 일할 의자": "Chairs for extended desk work",
  "작업·학업에 쓸 노트북": "Laptops for work or study",
  "쌀쌀할 때 걸칠 니트와 가디건": "Sweaters and cardigans for cooler weather",
  "단정하게 입을 셔츠·블라우스": "Shirts and blouses for a polished look",
  "편하게 입는 후드·맨투맨": "Hoodies and sweatshirts for casual wear",
  "일상에서 입을 데님": "Denim for everyday wear",
  "출근·일상용 바지": "Pants for work or everyday wear",
  "음악·통화에 쓸 유선·무선 이어폰": "Wired or wireless earphones for music and calls",
  "집·이동 중 사용할 헤드폰": "Headphones for home or on the go",
  "작업·게임용 키보드와 마우스": "Keyboards and mice for work or gaming",
  "업무·게임·영상용 모니터": "Monitors for work, gaming, or video",
  "운동·알림·일상용 스마트워치": "Smartwatches for fitness, notifications, and everyday use",
  "거실에 둘 커피테이블": "Coffee tables for the living room",
  "책과 소품을 정리할 책장": "Bookcases for organizing books and decor",
};

export function categoryLabel(category: string): string {
  return IS_ENGLISH_STUDY ? (CATEGORY_EN[category] ?? category) : category;
}

export function categoryBlurb(blurb: string): string {
  return IS_ENGLISH_STUDY ? (CATEGORY_BLURB_EN[blurb] ?? blurb) : blurb;
}

type LocalizableProduct = {
  title: string;
  description?: string;
  attributes?: Record<string, unknown>;
};

function nonEmptyAttribute(product: LocalizableProduct, key: string): string | undefined {
  const value = product.attributes?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Use the preserved Amazon source fields on the separately built English study frontend. */
export function productTitle(product: LocalizableProduct): string {
  if (!IS_ENGLISH_STUDY) return product.title;
  return nonEmptyAttribute(product, "titleEn")
    ?? nonEmptyAttribute(product, "sourceTitleEn")
    ?? product.title;
}

export function productDescription(product: LocalizableProduct): string | undefined {
  if (!IS_ENGLISH_STUDY) return product.description;
  return nonEmptyAttribute(product, "descriptionEn")
    ?? nonEmptyAttribute(product, "sourceDescriptionEn");
}

// seed_ms_v2 가격은 USD 원가 × 1350으로 빌드됨 — 표시할 때 같은 환율로 역산해야
// 참가자의 달러 감각과 데이터가 일치한다. backend core/locale.KRW_PER_USD와 동일 유지.
const KRW_PER_USD = 1350;

/** 아마존 원본 정가(attributes.priceUsd) — 배포 KRW와 정합 검증된 상품에만 존재. */
export function productUsd(product: LocalizableProduct | null | undefined): number | null {
  const raw = Number(product?.attributes?.["priceUsd"]);
  return Number.isFinite(raw) && raw > 0 ? raw : null;
}

export function formatStudyPrice(value: number, priceUsd?: number | null): string {
  if (IS_ENGLISH_STUDY) {
    // 원본 USD 정가가 있으면 그대로($6.99), 없으면 빌드 환율 역산($6.96)
    const v = priceUsd && priceUsd > 0 ? priceUsd : value / KRW_PER_USD;
    return `$${v.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
  return `${value.toLocaleString("ko-KR")}원`;
}

export const STUDY_UI = {
  survey: {
    title: tr("사전 설문", "Pre-study Questionnaire"),
    submitError: tr("설문 제출에 실패했어요. 잠시 후 다시 시도해 주세요.", "We could not submit your responses. Please try again shortly."),
    ineligible: tr("참여 기준/동의에 '아니오'가 있어 연구 참여 대상이 아닙니다.", "Based on your responses, you are not eligible to participate in this study."),
    requiredRemaining: (count: number) => tr(`필수(참여기준·동의) ${count}개 남음`, `${count} required eligibility or consent ${count === 1 ? "item remains" : "items remain"}`),
    ready: tr("제출 준비 완료 — 제출 후 쇼핑 대화로 이동합니다.", "Ready to submit. You will proceed to the shopping task afterward."),
    skip: tr("건너뛰기", "Skip"),
    skipTitle: tr("응답 없이 바로 대화로 이동 (테스트용)", "Continue without responses (testing only)"),
    submitting: tr("제출 중…", "Submitting…"),
    submit: tr("제출하고 대화 시작하기", "Submit and Continue"),
    responseExcluded: tr("이 응답은 연구 참여 제외 사유입니다.", "This response makes you ineligible to participate in the study."),
    returnToProlific: tr("Prolific으로 돌아가기", "Return your submission on Prolific"),
  },
  tasks: {
    title: tr("수행할 쇼핑 과제 2개를 골라 주세요", "Choose two shopping tasks to complete"),
    description: tr(
      "아래 네 가지 쇼핑 상황 중 자신의 실제 상황에 비추어 답할 수 있는 과제 2개를 골라 주세요. 진행 순서는 무작위로 정해져요.",
      "From the four shopping situations below, choose two you can answer from your own real life. The order of the two tasks will be randomized.",
    ),
    inSession: tr("이번 과제", "Your task"),
    hTitle: tr("가장 잘 안다고 느끼는 제품군을 골라 주세요", "Choose the product category you feel you know best"),
    hDescription: tr(
      "아래 네 가지 쇼핑 과제 중, 현재 본인이 그 제품군에 대해 가장 잘 안다고 느끼는 과제 하나를 선택해 주세요.",
      "From the four shopping tasks below, choose the one whose product category you currently feel you know best.",
    ),
    lTitle: tr("가장 잘 모른다고 느끼는 제품군을 골라 주세요", "Choose the product category you feel you know least"),
    comprehensionQ: tr("시작 전에 확인할게요 — 이번 과제의 상황은 무엇인가요?", "Before you start — what is the situation in this task?"),
    comprehensionWrong: tr("과제 설명을 다시 읽고 골라 주세요.", "Please re-read the task description above and try again."),
    fitNotice: tr(
      "쇼핑을 마칠 때, 선택이 이 상황에 왜 맞는지 짧게 설명하게 됩니다.",
      "When you finish, you'll briefly explain why your choice fits this situation.",
    ),
    lDescription: tr(
      "나머지 세 과제 중, 현재 본인이 그 제품군에 대해 가장 잘 모른다고 느끼는 과제 하나를 선택해 주세요. 선택한 두 과제의 진행 순서는 무작위로 정해져요.",
      "From the remaining three tasks, choose the one whose product category you currently feel you know least. The order of your two tasks will be randomized.",
    ),
  },
  categories: {
    step: (step: number) => tr(`${step}단계 / 2단계`, `Step ${step} of 2`),
    familiarTitle: tr("평소 잘 아는 상품군 1개를 골라 주세요", "Choose one product category you know well"),
    unfamiliarTitle: tr("잘 모르는 상품군 1개를 골라 주세요", "Choose one product category you do not know well"),
    familiarDescription: tr("상품을 고를 때 무엇을 봐야 하는지 스스로 잘 안다고 느끼는 쪽이에요.", "Select categories for which you feel you know what to consider when choosing a product."),
    unfamiliarDescription: tr("이번에는 반대로, 잘 모른다고 느끼는 상품군이에요. 잘 아는 상품군부터 순서대로 진행해요.", "Now select a category you feel less familiar with. You will shop the familiar category first."),
    selected: (count: number, total: number) => tr(`선택 ${count}/${total}`, `Selected ${count}/${total}`),
    back: tr("이전", "Back"),
    next: tr("다음", "Next"),
    start: tr("첫 번째 쇼핑 시작", "Start the First Shopping Task"),
    starting: tr("시작하는 중…", "Starting…"),
    loadError: tr("카테고리를 불러오지 못했어요. 새로고침해 주세요.", "We could not load the product categories. Please refresh the page."),
    startError: tr("쇼핑을 시작하지 못했어요. 다시 눌러 주세요.", "We could not start the shopping task. Please try again."),
  },
  tutorial: {
    pageTitle: tr("시작 전에, 잠깐 둘러볼게요", "A Quick Tour Before You Begin"),
    categoryIntro: tr("쇼핑을 시작하는 방법부터 알려드릴게요.", "First, we will show you how to begin a shopping task."),
    chatIntro: tr("대화 화면의 핵심 기능을 짚어드릴게요.", "Next, we will introduce the key features of the conversation screen."),
    skip: tr("건너뛰기", "Skip Tutorial"),
    previous: tr("이전", "Back"),
    next: tr("다음", "Next"),
    start: tr("시작하기", "Start Study"),
    // 실제 과제 화면(/study/categories)과 반드시 같은 목록이어야 한다 — 구 카탈로그
    // 더미(블루투스 스피커 등)가 남아 튜토리얼과 실제 선택지가 달랐다 (2026-08-25 QA).
    // H/L 1단계 재현이므로 선택 표시는 1개만.
    demoCategories: tr(
      [
        { name: "홈 워크스페이스용 모니터", blurb: "집에서 주로 하는 작업에 맞는 모니터", on: true },
        { name: "매일의 이동 시간을 위한 헤드폰", blurb: "왕복 두 시간 대중교통 이동에 쓸 헤드폰", on: false },
        { name: "좁은 방에 맞는 작업 책상", blurb: "좁은 방에 작업 공간을 만들 책상", on: false },
        { name: "새 직장 첫 출근을 위한 셔츠", blurb: "첫 주에 입을 셔츠·블라우스", on: false },
      ],
      [
        { name: "A monitor for your home workspace", blurb: "For the work you mainly do at home", on: true },
        { name: "Headphones for your daily commute", blurb: "For about two hours a day on public transport", on: false },
        { name: "A desk for a small room", blurb: "To set up a workspace in a small room", on: false },
        { name: "A shirt for your first week at a new job", blurb: "A shirt or blouse for your first week", on: false },
      ],
    ),
    steps: tr(
      [
        { key: "categories", title: "쇼핑할 상품군을 먼저 골라요", body: "평소 잘 아는 상품군 1개 → 잘 모르는 상품군 1개, 두 단계로 골라요.\n고른 2개를 차례로 한 번씩 쇼핑하게 돼요." },
        { key: "chat", title: "에이전트와 대화해요", body: "원하는 걸 대화로 좁혀가요.\n에이전트가 더 묻거나 후보를 추천해줘요. (위는 예시 대화예요)" },
        { key: "products", title: "추천 상품", body: "기준에 맞춰 서로 다른 방향의 후보를 보여줘요.\n좌우로 넘기면서 비교할 수 있어요." },
        { key: "card-info", title: "카드에서 무엇을 보나요", body: "가격·평점·리뷰와 함께, 왜 이 상품을 골랐는지 이유가 적혀 있어요." },
        { key: "card-feedback", title: "카드에 반응해요", body: "카드 옆 좋아요·싫어요로 취향을 알려주세요.\n반응할수록 추천이 정확해져요." },
        { key: "panel", title: "오른쪽: 제가 이해한 기준", body: "대화에서 파악한 기준이 옆 패널에 실시간으로 쌓여요.\n지금 어떤 기준으로 추천하고 있는지 언제든 확인할 수 있어요." },
        { key: "criteria", title: "맞는지 알려주세요", body: "기준마다 '맞아요/아니에요'로 확인하고, 중요도를 조절하거나 문구를 직접 수정할 수 있어요.\n틀리게 이해했으면 꼭 바로잡아 주세요 — 다음 추천에 바로 반영돼요." },
        { key: "evidence", title: "왜 그렇게 이해했는지", body: "'근거'를 누르면, 제가 어떤 말·선택을 보고 그렇게 판단했는지 확인할 수 있어요." },
        { key: "conflict", title: "기준이 부딪힐 때", body: "앞에서 말씀하신 기준과 다르게 고르신 것 같을 때, 패널 위에 확인 카드가 떠요.\n어느 쪽을 우선할지 골라주시면 바로 반영할게요." },
        { key: "composer", title: "쇼핑을 마치면", body: "충분히 살펴보셨으면 위쪽 '이 쇼핑 마치기'를 눌러주세요.\n마친 뒤 이번 쇼핑에 대한 짧은 질문을 드려요." },
      ],
      [
        { key: "categories", title: "Choose Your Product Categories", body: "Pick the category you know best, then the one you know least.\nYou will complete one shopping task for each of the two categories." },
        { key: "chat", title: "Talk with the Shopping Agent", body: "Refine what you are looking for through conversation.\nThe agent may ask follow-up questions or recommend products. The conversation shown above is an example." },
        { key: "products", title: "Review Recommended Products", body: "The agent presents alternatives that represent different ways to meet your criteria.\nSwipe horizontally to compare them." },
        { key: "card-info", title: "Review Product Information", body: "Each card shows the price, rating, review count, and an explanation of why the product was recommended." },
        { key: "card-feedback", title: "Respond to Product Cards", body: "Use Like or Dislike to tell the agent what you think.\nYour feedback helps the agent refine its recommendations." },
        { key: "panel", title: "Review the Criteria the Agent Understood", body: "The side panel is updated with criteria inferred from the conversation.\nYou can review which criteria the agent is currently using." },
        { key: "criteria", title: "Confirm or Correct the Criteria", body: "For each criterion, select Yes or No, adjust its priority, or edit its wording.\nPlease correct misunderstandings so they can be reflected in subsequent recommendations." },
        { key: "evidence", title: "Inspect the Supporting Evidence", body: "Select Evidence to see which statements or actions led the agent to infer a criterion." },
        { key: "conflict", title: "Resolve Conflicting Criteria", body: "When your recent choice appears to conflict with an earlier criterion, a confirmation card appears.\nChoose which direction should take priority." },
        { key: "composer", title: "Finish the Shopping Task", body: "When you have explored enough products, select Finish This Shopping Task at the top.\nYou will then answer a short questionnaire about the task." },
      ],
    ),
  },
  chat: {
    title: tr("쇼핑 대화", "Shopping Conversation"),
    finishShort: tr("마치기", "Finish"),
    finish: tr("이 쇼핑 마치기", "Finish This Shopping Task"),
    browseGuide: tr(
      "추천을 여러 번 받아 비교해 보시고, 결정이 서면 '마치기'를 눌러 주세요.",
      "Compare a few rounds of recommendations, and press Finish when you've made up your mind.",
    ),
    earlyFinishTitle: tr("지금 마칠까요?", "Finish now?"),
    earlyFinishBody: (n: number) => tr(
      n === 0
        ? "아직 추천을 받아보지 않으셨어요. 더 비교하지 않고 마칠까요?"
        : `아직 추천을 ${n}번만 보셨어요. 더 비교하지 않고 마칠까요?`,
      n === 0
        ? "You haven't seen any recommendations yet. Finish without comparing?"
        : `You've only seen ${n} round${n === 1 ? "" : "s"} of recommendations. Finish without comparing more?`,
    ),
    earlyFinishStay: tr("계속 쇼핑하기", "Keep Shopping"),
    earlyFinishLeave: tr("그래도 마치기", "Finish Anyway"),
    // --- ours-v2 탐색 파일럿 전용 (OURS_V2 플래그) ---
    oursV2ChipGuide: tr(
      "대화하는 동안 시스템이 파악한 당신의 조건이 오른쪽에 표시됩니다. 맞게 파악했는지 확인하고, 어긋난 것은 바로잡아 주세요.",
      "As you chat, the system will show what it thinks you're looking for on the right side. Please check if it got your preferences right and adjust anything that feels off.",
    ),
    confidenceTitle: tr("마치기 전에", "Before you finish"),
    confidenceBody: tr(
      "지금 선택에 얼마나 확신이 드시나요? 다른 선택지를 더 살펴보시겠어요?",
      "How confident are you in your choice? Would you like to explore more options?",
    ),
    confidenceExplore: tr("더 살펴보기", "Explore More Options"),
    confidenceFinish: tr("확신해요 — 마칠게요", "I'm Confident — Finish"),
    // --- ours-v3 ---
    v3ShowRecs: tr("확인했어요 — 추천 보기", "Looks Right — Show Recommendations"),
    v3GateHint: tr(
      "오른쪽 기준을 확인·수정한 뒤 버튼을 눌러 주세요. 채팅으로 바로잡으셔도 됩니다.",
      "Check and fix the criteria on the right, then press the button. You can also correct them by typing.",
    ),
    v3Hypothesis: tr("가설", "Hypothesis"),
    oursV2NeedRounds: (n: number) => tr(
      `마치기 전에 추천을 2번 이상 받아 비교해 주세요. 지금까지 ${n}번 받으셨어요.`,
      `Please compare at least 2 rounds of recommendations before finishing. You've seen ${n} so far.`,
    ),
    catalogNote: tr(
      "상품은 연구용 카탈로그(2023년 Amazon 데이터)에서 제공됩니다 — 가격은 현재 시세와 다를 수 있고, 실제 구매는 이루어지지 않습니다. 답변 생성에는 20–45초가 걸릴 수 있어요.",
      "Products come from a research catalog (2023 Amazon data) — prices may differ from current listings, and no real purchase will be made. Replies may take 20–45 seconds.",
    ),
    finishLocked: tr(
      "추천을 2회 이상 받은 뒤 마칠 수 있어요.",
      "You can finish after receiving at least 2 rounds of recommendations.",
    ),
    greeting: tr("안녕하세요!", "Hello!"),
    prompt: tr("무엇을 찾아드릴까요?", "What can I help you find?"),
    example: tr("예", "Example"),
    inputPlaceholder: tr("무엇을 찾고 계세요?", "What are you looking for?"),
    agent: tr("쇼핑 에이전트", "Shopping Agent"),
    user: tr("나", "You"),
    system: tr("시스템", "System"),
    send: tr("전송", "Send"),
    stop: tr("중지", "Stop"),
    disclaimer: tr("AI 답변으로 정확하지 않은 정보가 포함될 수 있어요.", "AI responses may contain inaccurate information."),
    thinkingSteps: tr(
      ["말씀을 살펴보고 있어요…", "기준을 정리하고 있어요…", "맞는 상품을 고르고 있어요…"],
      ["Reviewing your request…", "Organizing your criteria…", "Finding suitable products…"],
    ),
    reloaded: tr("연결이 불안정해 대화를 다시 불러왔어요.", "The connection was unstable, so we reloaded the conversation."),
    sendFailed: tr("메시지 전송에 실패했어요.", "We could not send your message."),
    feedbackFailed: tr("피드백 전송에 실패했어요.", "We could not submit your feedback."),
    selectedProduct: tr(
      "이 상품을 선택으로 기록했어요 — 실제 구매는 이루어지지 않아요.",
      "Recorded as your pick — no real purchase is made.",
    ),
    dislikeRecorded: tr("싫어요가 반영됐어요 — 다음 추천에 참고할게요.", "Dislike recorded — we'll factor it into the next recommendations."),
    conflictFailed: tr("충돌 해결에 실패했어요.", "We could not resolve the conflicting criteria."),
    criterionFailed: tr("기준 반영에 실패했어요.", "We could not update the criterion."),
    saveFailed: tr("저장에 실패했어요 — 다시 시도해 주세요.", "We could not save your response. Please try again."),
  },
  surveyModal: {
    preTitle: tr("쇼핑을 시작하기 전에", "Before You Begin Shopping"),
    preDescription: (category: string) => tr(`${category}에 대한 지금의 생각을 알려주세요. 대화가 끝난 뒤 같은 질문을 한 번 더 드립니다.`, `Tell us what you currently think about ${category}. We will ask the same questions again after the conversation.`),
    preSubmit: tr("쇼핑 시작하기", "Start Shopping"),
    postTitle: tr("이번 쇼핑은 어떠셨나요?", "How Was This Shopping Task?"),
    postDescription: tr("방금 마친 대화를 떠올리며 답해 주세요.", "Please answer while thinking about the conversation you just completed."),
    next: tr("다음으로", "Continue"),
    finalTitle: tr("마지막으로 전체 경험에 대해", "Finally, Tell Us About Your Overall Experience"),
    finalDescription: tr("오늘 진행한 쇼핑 전체를 떠올리며 답해 주세요. 이 설문을 마치면 연구가 종료됩니다.", "Please think about all of today's shopping tasks. The study will end after this questionnaire."),
    finalSubmit: tr("제출하고 종료", "Submit and Finish"),
    submitting: tr("제출 중…", "Submitting…"),
    submit: tr("제출", "Submit"),
    saveFailed: tr("설문 저장에 실패했어요 — 다시 제출해 주세요.", "We could not save the questionnaire. Please submit it again."),
  },
  completion: {
    taskTitle: tr("이 쇼핑을 마쳤어요", "You Completed This Shopping Task"),
    remaining: (count: number) => tr(`남은 쇼핑 ${count}번이 있어요.`, `${count} shopping ${count === 1 ? "task remains" : "tasks remain"}.`),
    allTasks: tr("예정된 쇼핑을 모두 마쳤어요.", "You have completed all scheduled shopping tasks."),
    opening: tr("여는 중…", "Opening…"),
    nextTask: tr("다음 쇼핑으로 넘어가기", "Continue to the Next Shopping Task"),
    finalSurvey: tr("마지막 설문으로", "Continue to the Final Questionnaire"),
    doneTitle: tr("연구가 모두 끝났어요", "You Have Completed the Study"),
    doneBody: tr("참여해 주셔서 감사합니다. 응답은 모두 저장되었으며, 연구 목적으로만 사용됩니다.", "Thank you for participating. Your responses have been saved and will be used only for research purposes."),
    close: tr("이제 이 창을 닫으셔도 됩니다.", "You may now close this window."),
    prolificRedirecting: tr(
      "잠시 후 Prolific으로 자동 이동합니다…",
      "You will be redirected to Prolific in a few seconds…",
    ),
    prolificReturn: tr("Prolific으로 돌아가기", "Return to Prolific"),
  },
} as const;
