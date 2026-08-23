// English mirror of mainSurvey.ts (2026-08-13 measurement plan).
//
// Validated scales use the published English item wordings (Flynn & Goldsmith
// 1999; Heitmann et al. 2007; CRS-Que, Jin et al. 2024; S-TIAS, McGrath et al.
// 2025) with only the referent adapted to "this shopping agent".
// ⚠️ Before an English deployment, verify each item against the original
// articles word-for-word — wordings here were transcribed for structure and
// must be proofread against the sources.
//
// Question ids must match mainSurvey.ts exactly — answers are stored by id and
// canonicalized back to Korean option values (localizedMainSurvey.ts).
import { MQuestion, MSection, allQuestions } from "./mainSurvey";

export const LIKERT_MIN_EN = "Strongly disagree";
export const LIKERT_MAX_EN = "Strongly agree";

const lk = (id: string, label: string, reverse = false): MQuestion =>
  ({ id, label, type: "likert", ...(reverse ? { reverse } : {}) });
const sg = (id: string, label: string, options: string[]): MQuestion =>
  ({ id, label, type: "single", options });
const consent = (id: string, label: string): MQuestion =>
  ({ id, label, type: "single", options: ["Yes", "No"], required: true, excludeIf: "No" });

export const PRE_STUDY_INTRO_EN =
  "This is the pre-study questionnaire for a conversational shopping agent study. " +
  "There are no right or wrong answers; choose what best matches your experience. " +
  "It takes about 2 minutes.";

export const PRE_STUDY_EN: MSection[] = [
  {
    id: "consent",
    title: "Eligibility and Consent",
    desc: "We first confirm your eligibility for this study.",
    questions: [
      consent("PRE_C1", "Are you 19 years of age or older?"),
      consent("PRE_C2", "Have you shopped online within the last 3 months?"),
      consent("PRE_C3", "Do you agree that conversation logs, click/choice/rejection behavior, and survey responses may be recorded for research purposes?"),
    ],
  },
  {
    id: "demographics",
    title: "Basic Information",
    questions: [
      sg("DEM_AGE", "Please select your age group.", [
        "19–24", "25–29", "30–34", "35–39", "40–49", "50 or older",
      ]),
      sg("DEM_GENDER", "Please select your gender.", [
        "Woman", "Man", "Other / prefer not to say",
      ]),
      sg("DEM_JOB", "Please select your current employment status.", [
        "Student", "Employed", "Self-employed/Freelancer", "Homemaker", "Unemployed/Job-seeking", "Other",
      ]),
    ],
  },
  {
    id: "shopping_facts",
    title: "Shopping Experience",
    questions: [
      sg("FACT_SHOP_FREQ", "In the last 3 months, how often did you purchase or compare products online?", [
        "Not at all", "Less than once a month", "1–3 times a month", "1–2 times a week", "3+ times a week",
      ]),
      sg("FACT_AI_REC", "How often have you asked generative AI (ChatGPT, Claude, Gemini, etc.) for product recommendations or purchase advice?", [
        "Never", "1–2 times", "3–5 times", "1–3 times a month", "Weekly or more",
      ]),
      lk("FACT_COMPARE", "I tend to compare multiple candidates before purchasing a product."),
    ],
  },
];

export const PRE_STUDY_REQUIRED_IDS_EN = allQuestions(PRE_STUDY_EN)
  .filter((q) => q.required)
  .map((q) => q.id);

// Flynn & Goldsmith (1999) Subjective Knowledge — full 5 items, 2/4/5 reversed.
export const KNOWLEDGE_SECTIONS_EN: MSection[] = [
  {
    id: "subjective_knowledge",
    title: "Your Knowledge of “{category}”",
    questions: [
      // Flynn & Goldsmith(1999) 1번 문항의 관례적 adapted 형태 — 원문 표기("pretty much")는
      // 현대 영어에서 "얼추"로 읽히는 중의성이 있어 후속 문헌의 통용 표현을 따른다(2026-08-18).
      lk("SPK_1", 'I know a lot about "{category}".'),
      lk("SPK_2", 'I do not feel very knowledgeable about "{category}".', true),
      lk("SPK_3", 'Among my circle of friends, I am one of the "experts" on "{category}".'),
      lk("SPK_4", 'Compared to most other people, I know less about "{category}".', true),
      lk("SPK_5", 'When it comes to "{category}", I really do not know a lot.', true),
      sg("EXP_BUY", 'How many times have you purchased products in the "{category}" category yourself?', [
        "Never", "Once", "2–3 times", "4+ times",
      ]),
      lk("INIT_CLARITY", 'Right now, I clearly know what to look for when choosing a product in the "{category}" category.'),
    ],
  },
];

// Heitmann et al. (2007) Choice Confidence — adapted to 7 points, item 1 reversed.
export const POST_TASK_EN: MSection[] = [
  {
    id: "choice_confidence",
    title: "Confidence in Your Final Choice",
    desc: "Please answer with the shopping task you just completed in mind.",
    questions: [
      { ...lk("CC_1", "It was impossible to be sure which product best matched my preferences.", true), points: 9 },
      { ...lk("CC_2", "I was confident I could single out the one product that best matched my preferences."), points: 9 },
      { ...lk("CC_3", "I am confident that I found the product that best meets my needs."), points: 9 },
    ],
  },
];

export const AUDIT_NECESSITY_EN = ["Had to be met", "Preferably met", "Not important in the end"] as const;
export const AUDIT_INFLUENCE_EN = ["Yes", "No", "Hard to say"] as const;

export const CRITERION_CHECK_EN: MQuestion[] = [
  sg("CRIT_MATCH", "How well does this criterion, shown by the agent, match the criteria you actually used?", [
    "Matches exactly", "Partially matches; needs revision", "Not my criterion",
  ]),
  sg("CRIT_FORMATION", "When did this criterion become important to you?", [
    "Important before the conversation, and I stated it from the start",
    "Important before the conversation, but I did not state it at first",
    "Became important during the conversation after seeing products or comparisons",
    "I adopted it after the agent suggested it",
    "It is not actually my criterion",
  ]),
];

// Raw NASA-TLX (Hart 1986; RTLX, pairwise weights omitted) — guardrail. Original
// NASA wording; PERFORMANCE keeps the original direction (0=Good) so all six read high=load.
const tlx = (id: string, label: string, minLabel: string, maxLabel: string): MQuestion =>
  ({ id, label, type: "slider", minLabel, maxLabel, required: true });

export const POST_STUDY_EN: MSection[] = [
  {
    id: "nasa_tlx",
    title: "Workload (both shopping tasks)",
    desc: "The following items are about your overall experience interacting with the shopping agent across the two shopping tasks you just completed. Exclude filling in surveys; think only of exploring and comparing products and deciding on a final choice. Rate each item from 0 to 100.",
    questions: [
      tlx("TLX_MENTAL", "How much mental and perceptual activity was required (e.g., thinking, deciding, remembering, looking, searching)? Was the task easy or demanding, simple or complex?", "Very low", "Very high"),
      tlx("TLX_PHYSICAL", "How much physical activity was required (e.g., pressing, moving, typing and operating)? Was the task easy or physically demanding?", "Very low", "Very high"),
      tlx("TLX_TEMPORAL", "How much time pressure did you feel due to the rate or pace at which the task elements occurred? Was the pace slow and leisurely or rapid and frantic?", "Very low", "Very high"),
      tlx("TLX_PERFORMANCE", "How successful do you think you were in accomplishing the goals of the task? How satisfied were you with your performance in accomplishing these goals?", "Good / successful", "Poor / unsuccessful"),
      tlx("TLX_EFFORT", "How hard did you have to work (mentally and physically) to accomplish your level of performance?", "Very low", "Very high"),
      tlx("TLX_FRUSTRATION", "How insecure, discouraged, irritated, stressed, and annoyed were you during the task?", "Very low", "Very high"),
    ],
  },
  {
    id: "understanding",
    title: "Agent Understanding",
    questions: [
      lk("CUI_1", "This shopping agent understood what I said."),
      lk("CUI_2", "I felt this shopping agent understood what I wanted."),
      lk("CUI_3", "I felt this shopping agent understood my purchase intentions."),
    ],
  },
  {
    id: "transparency",
    title: "Transparency",
    questions: [
      lk("TR_1", "I understood why the products were recommended to me."),
      lk("TR_2", "I understood how the system judged the suitability of the products."),
      lk("TR_3", "I understood how well the recommendations matched my preferences."),
    ],
  },
  {
    id: "control",
    title: "User Control",
    questions: [
      lk("UC_1", "I felt in control of modifying my preferences using this shopping agent."),
      lk("UC_2", "I was in control of the recommendations this shopping agent presented to me."),
      lk("UC_3", "I felt in control of adjusting the recommendations according to my preferences."),
    ],
  },
  {
    id: "satisfaction",
    title: "Satisfaction with Recommendations",
    questions: [
      lk("SAT_1", "I am satisfied with the recommendations this shopping agent provided."),
      lk("SAT_2", "The recommendations this shopping agent provided were satisfactory."),
      lk("SAT_3", "Overall, the recommendations of this shopping agent satisfied me."),
    ],
  },
  {
    id: "trust",
    title: "Trust in the AI Shopping Agent",
    questions: [
      lk("TRUST_1", "I am confident in this AI shopping agent."),
      lk("TRUST_2", "This AI shopping agent is dependable."),
      lk("TRUST_3", "I can trust this AI shopping agent."),
    ],
  },
  {
    id: "intention",
    title: "Intention to Use",
    questions: [
      lk("ITU_1", "I will use this shopping agent again."),
      lk("ITU_2", "I will use this shopping agent frequently."),
      lk("ITU_3", "I will tell my friends about this shopping agent."),
    ],
  },
  {
    id: "exploration_narrowing",
    title: "Your Exploration Experience",
    questions: [
      {
        id: "OPEN_NARROWING",
        type: "text",
        label: "While talking with the agent, did you ever feel that what the agent presented or emphasized narrowed your exploration more than necessary, or kept you from fully considering other important criteria or products? If not, write 'None'. If so, describe the situation and how it affected your choice.",
        placeholder: "Write 'None' if this did not happen",
        required: true,
      },
    ],
  },
];
