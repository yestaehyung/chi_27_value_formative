"""ValueCommit 온톨로지 어휘(닫힌 라벨) — **단일 출처**.

여기 있는 것: 이론으로 정해진 '닫힌 라벨 집합'(화행·가치축·동기·관계).
여기 없는 것: 런타임에 무한 생성되는 인스턴스의 '구조'(IntentionTopic/Concept 등) →
            그건 app/db/models.py(SQLAlchemy)가 정본이다.

즉 이 시스템의 온톨로지는 두 곳에 나뉜다 (중복이 아니라 종류가 다른 진실):
  - schema.py  : 어휘(vocabulary) — 닫힌 라벨. 오타 방지·자동완성·한눈에 보기.
  - models.py  : 저장 구조(persistence) — 노드/엣지가 DB에 앉는 형태.

str-Enum이라 기존 문자열 코드와 호환된다 (ValueAnchor.FUNCTIONAL == "Functional").
근거 문헌: TCV5(Sheth/Newman/Gross 1991), 동기(Arnold&Reynolds 2003),
관계 성질(RIG paper arXiv:2412.11500), 화행(PSCon taxonomy).
"""
from enum import Enum


class DialogueAct(str, Enum):
    """화행 — 사용자가 발화로 '무엇을 하는가' (PSCon taxonomy).
    ※ 가치 의도(IntentionTopic)와 다름. action_selector가 다음 행동 결정에 사용."""
    REVEAL = "reveal"        # 원하는 상품/조건/선호를 드러냄
    INTERPRET = "interpret"  # 기존 요구 구체화·반응
    REVISE = "revise"        # 요구/추천 수정
    INQUIRE = "inquire"      # 가격·이유·기능 등 정보 문의
    ACCEPT = "accept"        # 추천 수락
    REJECT = "reject"        # 추천 거절
    CHITCHAT = "chitchat"    # 잡담


class ValueAnchor(str, Enum):
    """가치 축 — TCV5 (Sheth/Newman/Gross 1991). '이 대안이 왜 가치 있나'(choice level)."""
    FUNCTIONAL = "Functional"    # 성능·신뢰성·내구성·가격 대비 효용
    SOCIAL = "Social"            # 사회집단 연상·사회적 이미지
    EMOTIONAL = "Emotional"      # 긍정/부정 정서 (안심·신뢰 / 불안·후회 회피)
    EPISTEMIC = "Epistemic"      # 호기심·새로움·정보 탐색·지식
    CONDITIONAL = "Conditional"  # 특정 상황·맥락 의존 효용


class MotivationDim(str, Enum):
    """쇼핑 동기 — Arnold&Reynolds 2003 hedonic 6 + Babin utilitarian. '왜 쇼핑하나'(activity level)."""
    ADVENTURE = "Adventure"            # 탐험·우연한 발견·새로움
    GRATIFICATION = "Gratification"    # 스트레스 해소·자기보상
    ROLE = "Role"                      # 타인을 위한 쇼핑의 즐거움 (선물)
    BARGAIN_VALUE = "BargainValue"     # 할인·득템의 즐거움
    SOCIAL_SHOPPING = "SocialShopping" # 함께 고르기·타인 반응
    IDEA = "Idea"                      # 트렌드·신제품·영감 탐색
    UTILITARIAN = "Utilitarian"        # 목적 달성·효율·과업 종료


class RelationType(str, Enum):
    """의도 간 관계 타입 (8종). relation_classifier가 분류."""
    CONFLICTS_WITH = "CONFLICTS_WITH"
    SUPPORTS = "SUPPORTS"
    PRIORITIZES = "PRIORITIZES"
    REVISES = "REVISES"
    WEAKENS = "WEAKENS"
    RESOLVES = "RESOLVES"
    MOTIVATES = "MOTIVATES"
    REFINES = "REFINES"


class RelationNature(str, Enum):
    """관계 성질 메타분류 (RIG paper arXiv:2412.11500)."""
    CO_OCCURRENCE = "co_occurrence"  # 동시적 — 한 세션 안에서 함께 나타남
    TEMPORAL = "temporal"            # 비동시적 — 시간 순서로 뒤가 앞을 바꿈
    CAUSAL = "causal"                # 인과 — 한 의도가 다른 의도를 유발


# 관계 타입 → 성질 (RIG ideation 1)
RELATION_TYPE_TO_NATURE: dict[str, str] = {
    RelationType.CONFLICTS_WITH.value: RelationNature.CO_OCCURRENCE.value,
    RelationType.SUPPORTS.value: RelationNature.CO_OCCURRENCE.value,
    RelationType.PRIORITIZES.value: RelationNature.CO_OCCURRENCE.value,
    RelationType.REVISES.value: RelationNature.TEMPORAL.value,
    RelationType.WEAKENS.value: RelationNature.TEMPORAL.value,
    RelationType.RESOLVES.value: RelationNature.TEMPORAL.value,
    RelationType.MOTIVATES.value: RelationNature.CAUSAL.value,
    RelationType.REFINES.value: RelationNature.CAUSAL.value,
}


# ── 하위호환 별칭: 기존 코드가 참조하는 리스트/튜플 (값은 위 Enum이 단일 출처) ──
DIALOGUE_ACTS: tuple[str, ...] = tuple(a.value for a in DialogueAct)
VALUE_ANCHORS: tuple[str, ...] = tuple(a.value for a in ValueAnchor)
TRAIT_ANCHORS = VALUE_ANCHORS                       # 내부명 호환 (anchor_mapper)
MOTIVATION_DIMS: tuple[str, ...] = tuple(m.value for m in MotivationDim)
RELATION_TYPES: tuple[str, ...] = tuple(r.value for r in RelationType)


def is_value_anchor(name: str) -> bool:
    return name in VALUE_ANCHORS
