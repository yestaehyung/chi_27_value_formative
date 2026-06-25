"""SQLAlchemy models matching spec §19.2 DDL.

온톨로지 표지(signpost): 이 파일은 런타임 그래프의 **저장 구조**(노드=테이블 행,
엣지=관계 테이블)가 정본이다. 닫힌 **라벨 어휘**(화행·TCV5·동기·관계 타입)는
app/ontology/schema.py 가 단일 출처 — 닫힌 컬럼은 거기 Enum을 사용한다.

sellers / product_metrics are folded into products for the MVP; the normalized
Product schema (§6.1) keeps the door open for joining real Naver source tables
(product_info / review_detail / purchase_detail / sme_static / sme_dynamic) later.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Enum as SAEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.ontology.schema import RelationType, ValueAnchor

# 닫힌 라벨 컬럼은 schema.py Enum으로 검증한다 (native_enum=False → SQLite엔 VARCHAR 저장,
# 물리 타입·마이그레이션 변경 없음. 잘못된 라벨만 ORM 레벨에서 차단). values_callable로
# Enum.value("Functional")가 저장되게 한다(이름 'FUNCTIONAL'이 아니라).
_ANCHOR_ENUM = SAEnum(ValueAnchor, native_enum=False, length=32,
                      values_callable=lambda e: [m.value for m in e])
_RELTYPE_ENUM = SAEnum(RelationType, native_enum=False, length=32,
                       values_callable=lambda e: [m.value for m in e])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Participant(Base):
    """세션을 넘나드는 사용자 단위. trait(TCV) 가치는 참가자에 누적되고,
    자연어 명세 파일도 참가자 1개로 유지된다 (2층 모델: trait는 안정적 특성)."""

    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str | None] = mapped_column(String)
    # 점점 보완되는 사용자 자연어 명세(=AI memory / intent spec). KG의 사람용 렌더링.
    spec_markdown: Mapped[str | None] = mapped_column(Text)
    spec_version: Mapped[int] = mapped_column(Integer, default=0)
    # FS1 사전 설문 응답 (raw answers + 파생 profile) — 참가자 프로파일링용
    survey: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)  # manual | simulation
    scenario_id: Mapped[str] = mapped_column(String, nullable=False)
    user_agent_id: Mapped[str | None] = mapped_column(String)
    participant_id: Mapped[str | None] = mapped_column(String)
    current_stage: Mapped[str] = mapped_column(String, nullable=False, default="exploration")
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(default=None)


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # user | service_agent | user_agent | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # dialogue_acts: 발화의 화행(PSCon taxonomy: reveal/inquire/accept...).
    # ※ IntentionTopic(가치 의도)과 다름 — 이건 "말로 뭘 하나"(대화 행위). 2026-06-22 intent→dialogue_act 개명.
    dialogue_acts: Mapped[list] = mapped_column(JSON, default=list)
    agent_action: Mapped[str | None] = mapped_column(String)
    related_product_ids: Mapped[list] = mapped_column(JSON, default=list)
    raw_llm: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    brand: Mapped[str | None] = mapped_column(String)
    price: Mapped[int | None] = mapped_column(Integer)
    list_price: Mapped[int | None] = mapped_column(Integer)
    discount_rate: Mapped[float | None] = mapped_column(Float)
    delivery_fee: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    long_term_review_ratio: Mapped[float | None] = mapped_column(Float)
    recent_sales_count: Mapped[int | None] = mapped_column(Integer)
    seller_id: Mapped[str | None] = mapped_column(String)
    seller_name: Mapped[str | None] = mapped_column(String)
    seller_grade: Mapped[str | None] = mapped_column(String)
    seller_years: Mapped[float | None] = mapped_column(Float)
    seller_region: Mapped[str | None] = mapped_column(String)
    image_url: Mapped[str | None] = mapped_column(String)
    product_url: Mapped[str | None] = mapped_column(String)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)  # 라벨 태그 — BM25 문서 + 태그 필터/근거
    description: Mapped[str | None] = mapped_column(Text)
    cue_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class ProductImpression(Base):
    __tablename__ = "product_impressions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    rank: Mapped[int] = mapped_column(Integer, default=0)
    recommendation_reason: Mapped[str | None] = mapped_column(Text)
    matched_intentions: Mapped[list] = mapped_column(JSON, default=list)
    weak_intentions: Mapped[list] = mapped_column(JSON, default=list)
    product_cues_shown: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    turn_id: Mapped[str | None] = mapped_column(ForeignKey("turns.id"))
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    type: Mapped[str] = mapped_column(String, nullable=False)
    valence: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String)
    reason_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class IntentionTopic(Base):
    __tablename__ = "intention_topics"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="inferred")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    explicitness: Mapped[str] = mapped_column(String, nullable=False, default="implicit")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    related_product_ids: Mapped[list] = mapped_column(JSON, default=list)
    # extra hints used by state builder (impliedHardConstraint / impliedAvoidance / kind)
    hints: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class IntentionEvidence(Base):
    """대화-의도 증거 엣지 (graph design D1).

    explicitness는 의도 노드가 아니라 증거 채널의 속성이다: 같은 의도가
    발화(explicit 엣지)와 반응(latent 엣지) 양쪽에서 지지될 수 있다.
    노드 수준 hidden 정의 = "explicit 엣지가 하나도 없는 의도".
    IntentionTopic.explicitness 컬럼은 파생 캐시로 유지된다 (merge.py가 갱신).
    """

    __tablename__ = "intention_evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"))
    evidence_type: Mapped[str] = mapped_column(String, nullable=False)  # turn | feedback | product_cue | unknown
    evidence_id: Mapped[str] = mapped_column(String, nullable=False)
    # channel = merge 시점의 source (user_utterance | feedback | product_comparison
    #           | wimhf_discovery | agent_inference)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    explicitness: Mapped[str] = mapped_column(String, nullable=False)  # explicit | implicit | latent — per edge
    kind: Mapped[str | None] = mapped_column(String)  # constraint | context | preference | avoidance
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Concept(Base):
    __tablename__ = "concepts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    normalized_label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    source_topic_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="llm")
    # 이론모듈 §11 — hybrid ontology node lifecycle & provenance
    status: Mapped[str] = mapped_column(String, default="observed")
    # seed|observed|candidate|validated|confirmed|revised|rejected|deprecated
    origin: Mapped[list] = mapped_column(JSON, default=list)  # top_down_seed|bottom_up_feature|user_correction|llm_extraction
    version: Mapped[float] = mapped_column(Float, default=1.0)
    scenario_scope: Mapped[list] = mapped_column(JSON, default=list)
    user_visible_label: Mapped[str | None] = mapped_column(String)
    sme_translation: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TopicConcept(Base):
    __tablename__ = "topic_concepts"

    topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"), primary_key=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


class ConceptAnchorMapping(Base):
    """개념 → 이론(value anchor) canonical 매핑 (ideation 2번).

    의도(topic)별 AnchorMapping을 개념에 연결된 모든 topic에 걸쳐 집계한 것.
    개념은 세션을 넘나드는 재사용 단위(TBox)이므로 이 매핑이 '개념이 어떤 이론에
    속하는가'의 안정적 정답이 된다. 의도는 자기 개념을 통해 이론을 상속한다.
    """

    __tablename__ = "concept_anchor_mappings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concepts.id"))
    anchor: Mapped[str] = mapped_column(_ANCHOR_ENUM, nullable=False)  # TCV5 (schema.ValueAnchor)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String, default="inferred")
    support_count: Mapped[int] = mapped_column(Integer, default=1)  # 집계에 기여한 topic 수


class AnchorMapping(Base):
    __tablename__ = "anchor_mappings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"))
    anchor: Mapped[str] = mapped_column(_ANCHOR_ENUM, nullable=False)  # TCV5 (schema.ValueAnchor)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # intensity (이론모듈 §7.3)
    confidence: Mapped[str] = mapped_column(String, nullable=False, default="inferred")
    # 이론모듈 §7.3 — 5-field anchor mapping
    evidence_strength: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    decision_impact: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    temporal_status: Mapped[str] = mapped_column(String, default="active")  # emerging|active|weakened|resolved
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class IntentionRelation(Base):
    __tablename__ = "intention_relations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    source_topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"))
    target_topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"))
    type: Mapped[str] = mapped_column(_RELTYPE_ENUM, nullable=False)  # 관계 타입 (schema.RelationType)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    rationale: Mapped[str | None] = mapped_column(Text)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    # graph design D4 — 인과(MOTIVATES/REFINES) 엣지 검증.
    # unverified | llm_thresholded | llm_downgraded
    # | judge_supported | judge_downgraded | judge_rejected   (M5 judge 평결)
    # | human_verified | human_rejected                        (권위 서열 최상위)
    verification: Mapped[str] = mapped_column(String, default="unverified")
    plausibility: Mapped[float | None] = mapped_column(Float)  # causal_evidence의 파생 캐시 (levels.py)
    causal_evidence: Mapped[str | None] = mapped_column(String)  # stated_cause|strong_inference|weak (M1 원본)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PreferenceStateSnapshot(Base):
    __tablename__ = "preference_state_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(String)  # 이론모듈 §8 value trajectory용
    anchor_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)  # §7.3 intensity/confidence 분해
    motivation_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # 동기 층(Hedonic6+Utilitarian) 0~1
    active_topic_ids: Mapped[list] = mapped_column(JSON, default=list)
    active_concept_ids: Mapped[list] = mapped_column(JSON, default=list)
    anchor_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    hard_constraints: Mapped[list] = mapped_column(JSON, default=list)
    # 구조화 예산 — LLM이 추출한 숫자 그대로(원). 문자열 파싱 없이 산수로 필터. 없으면 null.
    price_min: Mapped[int | None] = mapped_column(Integer)
    price_max: Mapped[int | None] = mapped_column(Integer)
    soft_preferences: Mapped[list] = mapped_column(JSON, default=list)
    avoidances: Mapped[list] = mapped_column(JSON, default=list)
    priority_order: Mapped[list] = mapped_column(JSON, default=list)
    uncertainty: Mapped[dict] = mapped_column(JSON, default=dict)
    user_visible_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class PreferenceConflict(Base):
    __tablename__ = "preference_conflicts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    severity: Mapped[str] = mapped_column(String, nullable=False)  # direct | ambiguous | weak
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    old_topic_id: Mapped[str | None] = mapped_column(String)
    new_topic_id: Mapped[str | None] = mapped_column(String)
    old_assumption: Mapped[str | None] = mapped_column(Text)
    new_signal: Mapped[str | None] = mapped_column(Text)
    conflict_type: Mapped[str] = mapped_column(String, nullable=False)
    explanation_for_user: Mapped[str | None] = mapped_column(Text)
    explanation_for_researcher: Mapped[str | None] = mapped_column(Text)
    suggested_resolutions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)


class ConflictResolutionEvent(Base):
    __tablename__ = "conflict_resolution_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conflict_id: Mapped[str] = mapped_column(ForeignKey("preference_conflicts.id"))
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    selected_option_id: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String, nullable=False)
    manual_text: Mapped[str | None] = mapped_column(Text)
    resulting_snapshot_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ChosenRejectedPair(Base):
    __tablename__ = "chosen_rejected_pairs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    prompt_context: Mapped[str] = mapped_column(Text, nullable=False)
    chosen_type: Mapped[str] = mapped_column(String, nullable=False, default="product")
    rejected_type: Mapped[str] = mapped_column(String, nullable=False, default="product")
    chosen_id: Mapped[str] = mapped_column(String, nullable=False)
    rejected_id: Mapped[str] = mapped_column(String, nullable=False)
    label_source: Mapped[str] = mapped_column(String, nullable=False)
    user_reason_text: Mapped[str | None] = mapped_column(Text)
    product_diff: Mapped[dict] = mapped_column(JSON, default=dict)
    response_diff: Mapped[dict] = mapped_column(JSON, default=dict)
    inferred_hidden_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class DiscoveredFeature(Base):
    __tablename__ = "discovered_features"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_pair_ids: Mapped[list] = mapped_column(JSON, default=list)
    example_pairs: Mapped[list] = mapped_column(JSON, default=list)
    candidate_anchor_mappings: Mapped[list] = mapped_column(JSON, default=list)
    novelty_score: Mapped[float | None] = mapped_column(Float)
    coverage_score: Mapped[float | None] = mapped_column(Float)
    predictiveness_score: Mapped[float | None] = mapped_column(Float)
    interpretability_score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, nullable=False, default="candidate")
    suggested_concept_label: Mapped[str | None] = mapped_column(String)
    suggested_ontology_action: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class CorrectionEvent(Base):
    """사용자가 chip(추론된 기준)을 수정한 이벤트 — '어떤 시점에 무엇을 어떻게' (S58 분석용)."""

    __tablename__ = "correction_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    topic_id: Mapped[str] = mapped_column(ForeignKey("intention_topics.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    # confirm | reject | increase_priority | decrease_priority | edit_label
    turn_index: Mapped[int] = mapped_column(Integer, default=0)  # 수정이 일어난 대화 시점
    before: Mapped[dict] = mapped_column(JSON, default=dict)  # {label,status,priority,confidence}
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    manual_label: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class ObservationMarker(Base):
    """Formative study 관찰 신호 (DG3·DG4).
    kind='marker'  — 연구자가 신뢰/불신/혼란 순간을 turn에 고정해 기록
    kind='inspect' — 사용자가 evidence drawer로 근거를 확인한 이벤트 (불신·검증 신호)
    """

    __tablename__ = "observation_markers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    turn_index: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="marker")
    tag: Mapped[str | None] = mapped_column(String)  # trust|distrust|confusion|correction_wish|inspect_evidence
    note: Mapped[str | None] = mapped_column(Text)
    topic_id: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class FeatureCluster(Base):
    """이론모듈 §9.4 Step 4 — 여러 pair에서 반복되는 feature를 묶은 상위 cluster."""

    __tablename__ = "feature_clusters"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    member_feature_ids: Mapped[list] = mapped_column(JSON, default=list)
    member_feature_labels: Mapped[list] = mapped_column(JSON, default=list)
    scenario_distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String)
    task: Mapped[str | None] = mapped_column(String)
    provider: Mapped[str | None] = mapped_column(String)
    request: Mapped[dict] = mapped_column(JSON, default=dict)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
