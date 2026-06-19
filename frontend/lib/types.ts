// Domain types matching spec §6-§11 (serialized camelCase from the backend)

// 7-anchor = TCV 5가치 + Hedonic/Utilitarian 쇼핑가치
export type ValueAnchor =
  | "Functional"
  | "Social"
  | "Emotional"
  | "Epistemic"
  | "Conditional"
  | "Hedonic"
  | "Utilitarian";

export type ProductCueSummary = {
  priceCue: "very_low" | "low" | "mid" | "high" | "very_high";
  trustCue: "low" | "medium" | "high";
  popularityCue: "niche" | "moderate" | "popular" | "very_popular";
  sellerCue: "new_or_low_grade" | "normal" | "trusted";
  noveltyCue?: "common" | "distinctive" | "unknown";
};

export type Product = {
  id: string;
  title: string;
  category?: string;
  brand?: string;
  price: number;
  listPrice?: number;
  discountRate?: number;
  imageUrl?: string;
  productUrl?: string;
  deliveryFee?: number;
  rating?: number;
  reviewCount?: number;
  longTermReviewRatio?: number;
  recentSalesCount?: number;
  sellerName?: string;
  sellerGrade?: string;
  attributes: Record<string, string | number | boolean>;
  description?: string;
  cueSummary: ProductCueSummary;
};

export type Turn = {
  id: string;
  sessionId: string;
  turnIndex: number;
  role: "user" | "service_agent" | "user_agent" | "system";
  content: string;
  intentLabels: string[];
  agentAction?: string;
  relatedProductIds: string[];
  createdAt: string;
};

export type Impression = {
  id: string;
  turnId: string;
  productId: string;
  rank: number;
  recommendationReason?: string;
  matchedIntentions: string[];
  weakIntentions: string[];
  product?: Product;
  createdAt: string;
};

export type FeedbackEvent = {
  id: string;
  turnId?: string;
  productId: string;
  type: string;
  valence: string;
  reasonCode?: string;
  reasonText?: string;
  createdAt: string;
};

export type PreferenceChip = {
  id: string;
  label: string;
  type: "must_have" | "important" | "nice_to_have" | "avoid" | "uncertain";
  userEditable: boolean;
  evidenceCount: number;
  displayRationale?: string;
  status?: string;
  priority?: string;
  confidence?: number;
};

export type UserVisibleSummary = {
  chips: PreferenceChip[];
  oneSentenceSummary: string;
  needsConfirmation: boolean;
};

export type PreferenceState = {
  id: string;
  turnIndex: number;
  stage?: string;
  activeTopicIds: string[];
  anchorScores: Record<ValueAnchor, number>;
  anchorBreakdown?: Record<string, {
    confirmedScore: number;
    contributors: {
      topicLabel: string; intensity: number; confidence: string;
      evidenceStrength: string; decisionImpact: string; temporalStatus: string;
      inConflict?: boolean; contribution: number;
    }[];
  }>;
  motivationScores?: Record<string, number>;
  hardConstraints: string[];
  softPreferences: string[];
  avoidances: string[];
  priorityOrder: string[];
  uncertainty: {
    unresolvedQuestions: string[];
    ambiguousTopics: string[];
    conflictIds: string[];
  };
  userVisibleSummary: UserVisibleSummary;
  createdAt: string;
};

export type ConflictResolutionOption = {
  id: string;
  label: string;
  action: string;
  resultingStatePreview: string;
};

export type Conflict = {
  id: string;
  severity: "direct" | "ambiguous" | "weak";
  status: string;
  oldAssumption?: string;
  newSignal?: string;
  conflictType: string;
  explanationForUser?: string;
  explanationForResearcher?: string;
  suggestedResolutions: ConflictResolutionOption[];
  createdAt: string;
  resolvedAt?: string;
};

export type AnchorMapping = {
  id: string;
  topicId: string;
  anchor: ValueAnchor;
  score: number;
  confidence: string;
  rationale?: string;
};

export type Concept = {
  id: string;
  label: string;
  normalizedLabel: string;
  createdBy: string;
  // 개념 → 이론 canonical 매핑 (ideation 2번)
  anchorMappings?: { anchor: ValueAnchor; score: number; confidence: string; supportCount: number }[] | null;
};

export type Topic = {
  id: string;
  label: string;
  description?: string;
  source: string;
  status: string;
  priority: string;
  confidence: number;
  explicitness: string;
  evidenceIds: string[];
  anchorMappings?: AnchorMapping[];
  concepts?: Concept[];
  createdAt: string;
};

export type Relation = {
  id: string;
  sourceTopicId: string;
  targetTopicId: string;
  type: string;
  strength: number;
  rationale?: string;
};

export type Pair = {
  id: string;
  sessionId: string;
  promptContext: string;
  chosenId: string;
  rejectedId: string;
  labelSource: string;
  userReasonText?: string;
  productDiff: {
    priceDiff?: number;
    chosenMoreExpensive?: boolean;
    longTermReviewRatioDiff?: number;
    sellerGradeDiff?: string;
    cueDifferences?: string[];
    naturalLanguageSummary?: string;
  };
  inferredHiddenReason?: string;
  chosenProduct?: Product;
  rejectedProduct?: Product;
  createdAt: string;
};

export type DiscoveredFeature = {
  id: string;
  label: string;
  description?: string;
  sourcePairIds: string[];
  examplePairs: { pairId: string; shortExplanation: string }[];
  candidateAnchorMappings: { anchor: ValueAnchor; score: number; rationale?: string }[];
  noveltyScore?: number;
  coverageScore?: number;
  predictivenessScore?: number;
  interpretabilityScore?: number;
  status: string;
  suggestedConceptLabel?: string;
  suggestedOntologyAction?: string;
  createdAt: string;
};

export type SessionInfo = {
  id: string;
  mode: string;
  scenarioId: string;
  currentStage: string;
  status: string;
  metadata: Record<string, unknown>;
  startedAt: string;
  endedAt?: string;
  turnCount?: number;
  feedbackCount?: number;
  pairCount?: number;
  conflictCount?: number;
  topicCount?: number;
};

export type Scenario = {
  id: string;
  title: string;
  initialUserNeed: string;
  targetCategory: string;
  recipient?: string;
  context?: string;
};

export type PersonaDemographics = {
  sex?: string;
  age?: number;
  marital_status?: string;
  family_type?: string;
  education_level?: string;
  occupation?: string;
  district?: string;
  province?: string;
  [k: string]: string | number | null | undefined;
};

export type Persona = {
  id: string;
  name: string;
  personaNarrative: string;
  // hand-authored trait personas (legacy pool)
  shoppingStyle?: string;
  traits?: Record<string, string>;
  valueOrientation?: Record<string, number>;
  // Nemotron-Personas-Korea pool
  source?: string;
  uuid?: string;
  demographics?: PersonaDemographics;
  narratives?: Record<string, string>;
};

export type EvidenceItem = {
  id: string;
  type: string;
  quote: string;
  role?: string;
  feedbackType?: string;
  productTitle?: string;
  productCues?: ProductCueSummary;
};

export type Snapshot = PreferenceState;
