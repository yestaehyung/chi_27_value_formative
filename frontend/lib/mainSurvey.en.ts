/**
 * English copy draft for the ValueCommit main study instruments.
 *
 * The participant flow selects this copy when NEXT_PUBLIC_STUDY_LOCALE=en.
 * Korean remains the default, and both deployments share the same page and
 * component implementation so ongoing flow changes do not need to be copied.
 *
 * Contract:
 * - Question, section, and construct IDs match `mainSurvey.ts`.
 * - PRE_TASK and POST_TASK use the same translated clarity items.
 * - English display choices are mapped back to the existing canonical values
 *   by localizedMainSurvey.ts before persistence.
 */

import type { MQuestion, MSection } from "./mainSurvey";

export const LIKERT_MIN_EN = "Strongly disagree";
export const LIKERT_MAX_EN = "Strongly agree";

const likert = (id: string, label: string): MQuestion => ({
  id,
  label,
  type: "likert",
});

const anchoredLikert = (
  id: string,
  label: string,
  minLabel: string,
  maxLabel: string,
  reverse = false,
): MQuestion => ({
  id,
  label,
  type: "likert",
  minLabel,
  maxLabel,
  reverse,
});

const single = (id: string, label: string, options: string[]): MQuestion => ({
  id,
  label,
  type: "single",
  options,
});

const consent = (id: string, label: string): MQuestion => ({
  id,
  label,
  type: "single",
  options: ["Yes", "No"],
  required: true,
  excludeIf: "No",
});

const CRITERIA_CLARITY_EN = [
  {
    key: "CLARITY_1",
    label: "I am clear about which criteria are important when choosing this product.",
  },
  {
    key: "CLARITY_2",
    label: "I am clear about which purchase criteria I should prioritize over others.",
  },
  {
    key: "CLARITY_3",
    label: "I can distinguish between must-have requirements and criteria I can compromise on.",
  },
] as const;

const clarityQuestions = (prefix: "TPRE" | "TPOST"): MQuestion[] =>
  CRITERIA_CLARITY_EN.map((item) =>
    likert(`${prefix}_${item.key}`, item.label),
  );

export const PRE_STUDY_INTRO_EN =
  "This is a pre-study questionnaire for a research study on conversational shopping agents. " +
  "There are no right or wrong answers. Please select the response that best reflects your usual experience. " +
  "It should take approximately 3 minutes.";

export const PRE_STUDY_EN: MSection[] = [
  {
    id: "consent",
    title: "Eligibility and Consent",
    desc: "Please confirm your eligibility to participate in this study.",
    questions: [
      consent("PRE_C1", "Are you 19 years of age or older?"),
      consent("PRE_C2", "Have you shopped online within the past three months?"),
      consent(
        "PRE_C3",
        "Do you agree that your conversation logs, clicks, selections, rejections, and survey responses may be recorded for research purposes?",
      ),
    ],
  },
  {
    id: "shopping",
    title: "Online Shopping Experience",
    questions: [
      single("PRE_1", "How often do you shop online?", [
        "Almost never",
        "Less than once a month",
        "Once or twice a month",
        "About once a week",
        "Several times a week",
        "Almost every day",
      ]),
    ],
  },
  {
    id: "llm",
    title: "Experience with LLM-based Chatbots",
    questions: [
      single(
        "PRE_2",
        "How often do you use AI chatbots such as ChatGPT, Claude, or Gemini?",
        [
          "Never used one",
          "Used one a few times",
          "Once or twice a month",
          "Once or twice a week",
          "Several times a week",
          "Almost every day",
        ],
      ),
      likert(
        "PRE_3",
        "I am comfortable refining a request through multiple turns of conversation with an AI.",
      ),
      likert(
        "PRE_4",
        "I am comfortable correcting an AI when it misunderstands my request.",
      ),
    ],
  },
  {
    id: "ai_rec",
    title: "Experience with AI Product Recommendations",
    questions: [
      single(
        "PRE_5",
        "Have you ever asked an AI for product recommendations or purchasing advice?",
        ["No", "Yes, a few times", "Yes, frequently"],
      ),
      single(
        "PRE_6",
        "Have you used AI product recommendations to compare products or make a purchase decision?",
        [
          "No",
          "Yes, as a reference when comparing products",
          "Yes, to make an actual purchase decision",
        ],
      ),
    ],
  },
  {
    id: "agent_knowledge",
    title: "Knowledge of AI Agents",
    questions: [
      likert(
        "PRE_7",
        "I am aware that an AI agent can infer and update a user's preferences based on a conversation.",
      ),
      likert(
        "PRE_8",
        "I am aware that an AI agent may misinterpret a user's intentions or product information.",
      ),
    ],
  },
  {
    id: "prior_trust",
    title: "Prior Trust in AI Product Recommendations",
    questions: [
      likert(
        "PRE_9",
        "I believe AI product recommendations can provide useful support for purchase decisions.",
      ),
      likert(
        "PRE_10",
        "For important purchases, I believe AI recommendations should be compared with or verified against other information.",
      ),
    ],
  },
];

export const PRE_STUDY_REQUIRED_IDS_EN = PRE_STUDY_EN.flatMap(
  (section) => section.questions,
)
  .filter((question) => question.required)
  .map((question) => question.id);

export const PRE_TASK_EN: MSection[] = [
  {
    id: "domain_knowledge",
    title: "Category Knowledge and Experience",
    questions: [
      likert("TPRE_K1", 'I am knowledgeable about "{category}."'),
      likert(
        "TPRE_K2",
        'I can evaluate the differences among products in the "{category}" category.',
      ),
      single(
        "TPRE_E1",
        'Have you personally purchased a product in the "{category}" category before?',
        ["No", "Yes, once", "Yes, two or more times"],
      ),
      single(
        "TPRE_E2",
        'Have you ever used a product in the "{category}" category?',
        [
          "No",
          "Yes, for less than one year",
          "Yes, for one year or longer",
        ],
      ),
    ],
  },
  {
    id: "criteria_clarity",
    title: "Clarity of Purchase Criteria",
    questions: clarityQuestions("TPRE"),
  },
];

export const POST_TASK_EN: MSection[] = [
  {
    id: "criteria_clarity",
    title: "Clarity of Purchase Criteria",
    desc: "These are the same questions you answered before the task. Please answer based on how you feel now.",
    questions: clarityQuestions("TPOST"),
  },
  {
    id: "intent_alignment",
    title: "Alignment with the User's Intent",
    questions: [
      likert(
        "TPOST_A1",
        "The agent understood the purchase criteria that were important to me.",
      ),
      likert(
        "TPOST_A2",
        "The agent understood why particular criteria mattered to me and the context behind them.",
      ),
      likert(
        "TPOST_A3",
        "The priorities the agent assigned to my criteria matched my own priorities.",
      ),
    ],
  },
  {
    id: "control",
    title: "User Control and Correctability",
    questions: [
      likert(
        "TPOST_U1",
        "I was able to correct the agent when it misunderstood me.",
      ),
      likert(
        "TPOST_U2",
        "I was able to adjust the purchase criteria used for recommendations in the direction I wanted.",
      ),
    ],
  },
  {
    id: "outcome",
    title: "Recommendation and Decision Outcomes",
    questions: [
      likert(
        "TPOST_O1",
        "The recommendations were appropriate for my current shopping goal and criteria.",
      ),
      likert(
        "TPOST_O2",
        "Overall, I was satisfied with the recommendations.",
      ),
      likert(
        "TPOST_O3",
        "I feel confident that I could choose a product based on these results.",
      ),
    ],
  },
  {
    id: "trust",
    title: "Trust in the Agent",
    questions: [
      likert(
        "TPOST_T1",
        "I could trust this agent's recommendations and interpretations.",
      ),
      likert(
        "TPOST_T2",
        "The agent appropriately communicated its limitations or uncertainty.",
      ),
    ],
  },
  {
    id: "tlx",
    title: "Task Load (NASA-TLX)",
    desc: "Please indicate how you felt while completing this task.",
    questions: [
      anchoredLikert(
        "TPOST_TLX_MENTAL",
        "How mentally demanding was this task?",
        "Very low",
        "Very high",
      ),
      anchoredLikert(
        "TPOST_TLX_PHYSICAL",
        "How physically demanding was this task?",
        "Very low",
        "Very high",
      ),
      anchoredLikert(
        "TPOST_TLX_TEMPORAL",
        "How much time pressure did you feel while completing this task?",
        "Very low",
        "Very high",
      ),
      anchoredLikert(
        "TPOST_TLX_PERFORMANCE",
        "How successful do you think you were in completing this task?",
        "Not at all successful",
        "Very successful",
        true,
      ),
      anchoredLikert(
        "TPOST_TLX_EFFORT",
        "How much effort did you have to exert to complete this task?",
        "Very low",
        "Very high",
      ),
      anchoredLikert(
        "TPOST_TLX_FRUSTRATION",
        "How frustrated or uncomfortable did you feel while completing this task?",
        "Very low",
        "Very high",
      ),
    ],
  },
];

export const POST_STUDY_EN: MSection[] = [
  {
    id: "overall",
    title: "Overall Experience",
    questions: [
      likert(
        "END_O1",
        "Overall, I liked the recommendations provided by this agent.",
      ),
      likert(
        "END_O2",
        "The agent understood what I was looking for.",
      ),
      likert("END_O3", "I felt that I could trust this agent."),
      likert(
        "END_O4",
        "I would like to use an agent like this for real-world shopping.",
      ),
    ],
  },
  {
    id: "interpretability",
    title: "Interpretability of the Agent's Understanding",
    questions: [
      likert(
        "END_I1",
        "I could easily understand which purchase criteria the agent was currently considering.",
      ),
      likert(
        "END_I2",
        "I could easily understand how important the agent considered each criterion to be.",
      ),
      likert(
        "END_I3",
        "The wording and amount of information used to present the purchase criteria were appropriate and easy to understand.",
      ),
    ],
  },
  {
    id: "evidence",
    title: "Validity and Traceability of Evidence",
    questions: [
      likert(
        "END_V1",
        "I could identify which of my statements or actions led the agent to infer each purchase criterion.",
      ),
      likert(
        "END_V2",
        "The evidence presented by the agent appropriately supported each inferred purchase criterion.",
      ),
      likert(
        "END_V3",
        "The evidence helped me judge whether the agent's interpretation was correct.",
      ),
    ],
  },
  {
    id: "edit_usability",
    title: "Usability of the Correction Interface",
    questions: [
      likert(
        "END_E1",
        "I could easily edit or remove purchase criteria that the agent inferred incorrectly.",
      ),
      likert(
        "END_E2",
        "I could easily adjust the priorities of my purchase criteria.",
      ),
      likert(
        "END_E3",
        "I could tell that my corrections were reflected in subsequent recommendations.",
      ),
    ],
  },
];

export const CRITERION_CHECK_EN: MQuestion[] = [
  single(
    "CRIT_MATCH",
    "Does this purchase criterion reflect what you actually thought?",
    ["Yes", "Partially", "No"],
  ),
  anchoredLikert(
    "CRIT_IMPORTANCE",
    "How important was this criterion to your actual purchase decision?",
    "Not at all important",
    "Extremely important",
  ),
  single(
    "CRIT_EVIDENCE",
    "Do the statements, selections, or rejections presented as evidence support this criterion?",
    ["Yes", "Partially", "No"],
  ),
  single(
    "CRIT_FORMATION",
    "When did this criterion form?",
    [
      "I had this criterion from the beginning but did not explicitly express it in the conversation.",
      "I already had this criterion, but it became clearer during the conversation.",
      "This criterion formed while I was exploring products and conversing with the agent.",
    ],
  ),
];

/**
 * Non-survey participant copy collected here for team review. These strings
 * mirror the current Korean flow, but are not consumed by components yet.
 */
export const MAIN_STUDY_UI_EN = {
  preStudy: {
    title: "Pre-study Questionnaire",
    submit: "Submit and Start",
    submitting: "Submitting…",
    ready: "Ready to submit. You will proceed to the shopping task afterward.",
    submitError: "We could not submit your responses. Please try again shortly.",
    ineligible: "Based on your responses, you are not eligible to participate in this study.",
  },
  tutorial: {
    title: "A Quick Tour Before You Begin",
    categoryIntro: "First, we will show you how to begin a shopping task.",
    chatIntro: "Next, we will introduce the key features of the conversation screen.",
    skip: "Skip Tutorial",
    next: "Next",
    start: "Start Study",
  },
  categories: {
    familiarTitle: "Choose two product categories you know well",
    familiarDescription:
      "Select categories for which you feel you already know what to consider when choosing a product.",
    unfamiliarTitle: "Choose two product categories you do not know well",
    unfamiliarDescription:
      "Now select categories you feel less familiar with. The task order will be randomized.",
    selected: "Selected",
    previous: "Back",
    next: "Next",
    start: "Start the First Shopping Task",
    starting: "Starting…",
    loadError: "We could not load the product categories. Please refresh the page.",
    startError: "We could not start the shopping task. Please try again.",
  },
  session: {
    agentName: "Shopping Agent",
    inputPlaceholder: "What are you looking for?",
    finishShopping: "Finish This Shopping Task",
    thinking: "Looking for a better answer…",
    disclaimer: "AI responses may contain inaccurate information.",
  },
  done: {
    title: "You Have Completed the Study",
    body: "Thank you for participating. Your responses have been saved and will be used only for research purposes.",
    close: "You may now close this window.",
  },
} as const;
