# 온톨로지 스키마 중앙화 설계

**날짜:** 2026-06-22
**상태:** 설계 → 구현
**범위:** 흩어진 고정 라벨을 `app/ontology/schema.py`로 중앙화 (Enum), 닫힌 DB 컬럼이 그 Enum을 사용하도록 전환

---

## 1. 문제

온톨로지의 **고정 라벨**(닫힌 집합, 이론 유래)이 코드 곳곳에 평범한 리스트/dict로 흩어져 있다:
- `anchor_mapper.py`: `TRAIT_ANCHORS`, `MOTIVATION_DIMS`
- `relation_classifier.py`: `RELATION_NATURE`
- 프롬프트 문자열: 화행 7종, relation type 8종

→ "시스템이 다루는 타입 체계"를 한눈에 볼 곳이 없고, 문자열로 써서 오타가 안 잡힌다. Zep의 `default_ontology.py`처럼 한 곳에 모으고 싶다.

## 2. 핵심 구분 (사용자 통찰)

| 종류 | 고정? | 처리 |
|------|:---:|------|
| DialogueAct, ValueAnchor, MotivationDim, RelationType, RelationNature | ✅ 닫힘 | **Enum → schema.py** |
| IntentionTopic, Concept | ❌ 런타임 무한 생성 | **구조는 models.py(SQLAlchemy) 정본 유지** — schema.py에 안 넣음 |

→ 라벨(vocabulary)과 구조(persistence)는 **다른 종류의 진실**. 두 파일로 나뉘는 게 중복이 아니라 올바른 분리 (Codex 자문 일치).

## 3. 결정 (Codex 자문 = 선택 iii)

- **D1.** 고정 라벨 → `app/ontology/schema.py`에 `str, Enum`으로. + 호환용 튜플(`VALUE_ANCHORS = tuple(a.value for a in ValueAnchor)`) 노출(프롬프트·테스트·기존 코드 호환).
- **D2.** 닫힌 스칼라 DB 컬럼 → SQLAlchemy `Enum(XxxEnum, native_enum=False)` 사용 (문자열 저장 유지 + 검증). 대상: `AnchorMapping.anchor`, `ConceptAnchorMapping.anchor`, `IntentionRelation.type`. (verification 등 일부는 값 종류 많아 2차 검토.)
- **D3.** `Turn.dialogue_acts`(JSON 리스트)는 JSON 저장 유지 + 입출력 경계에서 Enum 검증.
- **D4.** Topic/Concept을 Pydantic으로 중복 정의하지 않음 (DB 동기화 부담, 우리 규모 무가치).
- **D5.** schema.py + models.py 양쪽 상단에 표지 주석("닫힌 라벨=schema.py, 런타임 행=models.py"). docs도 갱신.
- **D6.** `str, Enum` 사용 → `ValueAnchor.FUNCTIONAL == "Functional"` 참 → **기존 문자열 코드와 호환**, 점진 전환 가능, 안 깨짐.

### 안전성 확인 (DB 실측 2026-06-22)
- `anchor_mappings.anchor`: Functional/Emotional/Social/Conditional/Epistemic — Enum과 일치 ✅
- `intention_relations.type`: MOTIVATES/REFINES/SUPPORTS/CONFLICTS_WITH — Enum 부분집합 ✅
- → 기존 데이터가 Enum 값과 정확히 일치 → 전환 안전.

## 4. schema.py 구조

```python
"""ValueCommit 온톨로지 어휘(닫힌 라벨) 단일 출처.
런타임 그래프 행(IntentionTopic/Concept 등 구조)은 app/db/models.py 가 정본."""
from enum import Enum

class DialogueAct(str, Enum):     # 화행 (PSCon)
    REVEAL="reveal"; INQUIRE="inquire"; ACCEPT="accept"; REJECT="reject"
    REVISE="revise"; INTERPRET="interpret"; CHITCHAT="chitchat"

class ValueAnchor(str, Enum):     # TCV5 (Sheth 1991)
    FUNCTIONAL="Functional"; SOCIAL="Social"; EMOTIONAL="Emotional"
    EPISTEMIC="Epistemic"; CONDITIONAL="Conditional"

class MotivationDim(str, Enum):   # 동기 (Arnold&Reynolds 2003)
    ADVENTURE="Adventure"; GRATIFICATION="Gratification"; ROLE="Role"
    BARGAIN_VALUE="BargainValue"; SOCIAL_SHOPPING="SocialShopping"
    IDEA="Idea"; UTILITARIAN="Utilitarian"

class RelationType(str, Enum):    # 의도간 관계 8종
    CONFLICTS_WITH="CONFLICTS_WITH"; SUPPORTS="SUPPORTS"; PRIORITIZES="PRIORITIZES"
    REVISES="REVISES"; WEAKENS="WEAKENS"; RESOLVES="RESOLVES"
    MOTIVATES="MOTIVATES"; REFINES="REFINES"

class RelationNature(str, Enum):  # 관계 성질 (RIG paper)
    CO_OCCURRENCE="co_occurrence"; TEMPORAL="temporal"; CAUSAL="causal"

RELATION_TYPE_TO_NATURE = { RelationType.CONFLICTS_WITH: RelationNature.CO_OCCURRENCE, ... }

# 기존 코드 호환 튜플/별칭
VALUE_ANCHORS = tuple(a.value for a in ValueAnchor)
MOTIVATION_DIMS = tuple(m.value for m in MotivationDim)
```

## 5. 마이그레이션 영향

- SQLAlchemy `native_enum=False` → SQLite엔 여전히 문자열(VARCHAR)로 저장 → **컬럼 타입 물리 변경 없음, 마이그레이션 불필요**. (검증만 ORM 레벨에서 추가)
- 기존 모듈(`anchor_mapper`, `relation_classifier`)의 리스트/dict는 schema.py를 import해 재정의(별칭 유지 → 하위호환).
- mock 24개 통과 유지가 합격 기준.

## 6. 안 하는 것
- 그래프 DB 전환 (규모 작음·결정론 테스트·단일파일 가치 — 별도 결정됨)
- Topic/Concept Pydantic 중복 정의
- DB 컬럼 물리 타입 변경
