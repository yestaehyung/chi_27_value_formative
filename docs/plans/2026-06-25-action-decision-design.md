# `action_decision` — LLM 기반 다음 행동 판단 (설계)

**Date:** 2026-06-25
**Status:** 구현 완료 + 실 LLM 검증 (revision 2026-06-26 아래 참조)

> **Revision (2026-06-26) — recommend-first 피벗.** 초안의 "추천 vs 질문 + 12축 probe" framing이
> 실 LLM(deepseek)에서 과잉질문을 유발했다(12축이 늘 비어 있어 "빈 축"이 항상 존재 → 영원히
> clarify, 같은 축 반복). 이는 TCV axiom 2(상황마다 *소수* 가치만 salient)와도 어긋난다.
> → **재정의: 에이전트는 추천 에이전트다. 기본 동작은 추천. 숨은 가치·동기는 commit engine에서
> background로 수동 감지(능동 심문 X) — 이게 원래 프로젝트 정체성이자 비간섭 detection이라는
> 연구 기여점.** clarify는 "무엇을 찾는지 전혀 감이 없을 때"만 드물게.
> 부수효과: "동기 probe가 죽었다"는 버그가 아니라 *의도된 설계*가 됨(동기는 감지만, 안 물음).
>
> **컨텍스트 버그 + 수정.** action_decision이 최신 발화 1줄 + 구조화 상태만 받아, 자유대화
> (category=None)에서 도메인(원피스)을 턴 너머로 잃고 데모 prior(이어폰 무선/유선)로 추락했다.
> → deep-research(2026-06-26, [[agent-memory-context-patterns]]) 권고대로 **belt-and-suspenders:
> 최근 N턴 원문 윈도우 + 구조화 상태**를 함께 전달(`build_action_decision_context`, window=6).
>
> **프롬프트.** 7-규칙 나열 → **역할 정의 한 줄**로 압축(role-led, [[prefers-positive-form-prompts]]).
> 실 LLM + 실 카탈로그(seed_naver) 검증: 원피스 대화에서 매 턴 원피스 추천, 무선/유선 누출 0,
> 과잉질문 0. 구현: `action_selector.py`·`service_agent.py`·`prompts.py`·`mock_rules.py`,
> 테스트 `tests/test_action_decision.py`.
**관련 메모:** [[prefers-llm-judgment-over-hardcoding]], [[tcv-vs-shopping-motivation-literature]], [[prefers-positive-form-prompts]]

## 1. 문제

추천 에이전트의 "추천할까 / 질문할까 + 무엇을 물을까" 판단이 **하드코딩 규칙**이라, 도메인·시나리오가 바뀌면 깨진다. 구체 증상(라이브 이어폰 대화에서 관측):

- **Path A** `action_selector.py:22` — `if category is None: clarify` 가 함수 첫 줄. 자유대화(custom 시나리오, `targetCategory=None`)면 **매 턴 무조건 clarify** → 사용자가 "헬스", "10만원", "바로 추천해주세요"를 줘도 영원히 질문만.
- **Path B** `should_value_clarify` — `non_context < 2` 임계값으로 첫 추천을 가로챔.
- **probe 3겹 하드코딩** — ① 언제(임계값) ② 무엇을(`"선물" in goal → Social` 키워드 매핑) ③ 뭐라고(차원별 고정 문자열 dict).
- **"바로 추천해줘"를 읽는 코드 없음** — 명시적 요구 무시.
- **동기 probe는 죽은 코드** — `motivation.py::next_probe` 호출처 0개. 동기는 측정·정렬엔 쓰지만 한 번도 *질문*하지 않음.

## 2. 목표 (연구 정렬)

이 프로토타입의 연구 주장은 **A**다(주장 B "LLM이 대화 정책 전체를 자율 운영"은 범위 밖):

> **① 사용자와 대화가 잘 되는 추천 에이전트 + ② 사용자의 가치·동기를 잘 파악.**
> RIG, 이론 두 개(TCV5 + 동기7)는 모두 ②를 더 잘하려는 재료. 지금 고치는 이유 = ①(대화)이 깨져서.

따라서 LLM이 가져야 할 판단은 정확히 **①을 고치고 ②를 수행하는 결정** = "추천할까 / (가치냐 동기냐) 무엇을 더 물을까". 그 외(충돌카드·구매종료)는 ①·②가 아닌 plumbing → 결정론 유지(교란 통제·재현성).

## 3. 설계 개요 — 하이브리드 (구조 가드 + LLM 결정기)

매 user 턴, `service_agent`에서 commit 직후(스냅샷 확보, 쓰기 락 해제 상태):

```
1) 구조적 가드 (실제 객체/사건 기반, LLM 아님):
   · direct conflict 존재        → show_conflict
   · accept + 추천이력           → close
   · inquire + 추천이력 + !reveal → explain
2) 그 외 → action_decision (LLM):
   → { action: recommend | clarify, reason, probe? }
```

`select_next_action`의 `category is None`·기본 recommend·reject/revise 분기와 `should_value_clarify` 오버라이드, 그리고 `build_value_question`/`next_probe`/RIG 질문 선택기를 **action_decision 하나로 통합**한다. 충돌·accept·inquire 가드는 `action_selector`에 남긴다.

## 4. action_decision task

**입력 (context):**
- `recentTurns`: 최근 N턴(사용자가 방금 한 말 — "바로 추천해줘" 포함)
- `values`: TCV5 점수 + confirmed/추측 구분 (snapshot.anchor_scores/anchor_breakdown)
- `motivations`: 동기7 점수 (snapshot.motivation_scores)
- `ragPrediction`: RIG 교차세션 예측(있으면) — 선제 질문 소스
- `signals`: hasRecommendations, scenarioGoal/category(있으면)

**출력:**
```json
{
  "action": "recommend" | "clarify",
  "reason": "왜 이렇게 정했는지 한 문장",
  "probe": { "dimension": "<TCV5 또는 동기7 중 1>", "question": "물어볼 말" }
}
```
- `probe`는 `action=="clarify"`일 때만. `dimension`은 **12 vocab(가치5+동기7)으로 제약** → "어느 축을 측정했나" 추적 가능(연구 분석).
- `question`은 LLM이 맥락에 맞게 저작(고정 dict 제거). RIG 예측이 강하면 그걸 선제 질문으로 쓸 수 있음.

## 5. 이론 근거 (deep-research 2026-06-25, 적대검증)

- **두 축 다 elicit**: 층위 구분(동기=활동/에피소드, 가치=선택/대상)은 문헌상 견고 + **두 이론을 대화로 동시에 끌어낸 선행연구 없음 → 기여 포인트**.
- **TCV는 상황적**(axiom 2) → 시나리오-국한 유지.
- **"동기→가치" 위계는 미검증** → control flow에 위계 박지 **않음**. 두 축 **대등**, 관계는 *측정 대상*으로 남김. (코드 주석 "동기가 가치를 조건짓는다"는 가설로 표기.)
- **중복 주의**: TCV functional≈utilitarian, emotional≈hedonic(층위는 다름) → 같은 걸 두 번 묻지 않게 프롬프트로 가드.

## 6. 배치 & 동시성

- `service_agent.handle_user_turn`에서 commit 이후 호출(스냅샷 필요). commit이 이미 `db.commit()`으로 락 해제 → **LLM 호출 중 쓰기 락 없음**(데드락 안전).
- 비용: 결정이 분기를 가르므로 critical path에 LLM 1콜 추가(순차). 연구 데모상 수용. (추후 다른 콜과 병합 여지 — 지금은 단순 우선.)

## 7. mock + 프롬프트 계약

기존 18개 task와 동일 패턴. `mock_rules.TASK_HANDLERS["action_decision"]` (결정론) + `prompts.SYSTEM_BY_TASK`/`FORMAT_BY_TASK["action_decision"]`(긍정형). mock 규칙(결정론, 도메인 무관):
- 사용자 발화에 명시적 추천 요구("추천", "바로", "보여줘") → recommend
- 비맥락 가치/동기 신호가 빈약하면 → clarify, 가장 비어있는 축 probe
- 그 외 → recommend
(24개 mock 테스트가 이 핸들러로 돈다 — 스마트워치 데모 재현 유지.)

## 8. 방어적 검증 (defense-in-depth)

LLM 출력을 현실과 대조:
- `probe.dimension`이 12 vocab 밖 → 드롭(폴백: 가장 불확실 가치 anchor).
- `action`이 recommend/clarify 외 → recommend로 정규화.
- clarify인데 `question` 비면 → B-폴백(기존 `build_value_question`).

## 9. 바뀌는 파일

- `app/agents/action_selector.py` — `category is None`·기본 recommend·reject/revise 제거; 충돌·accept·inquire 가드만 남김(또는 service_agent로 흡수).
- `app/agents/service_agent.py` — `should_value_clarify` 오버라이드 + RIG/value 질문 선택 블록(192–218)을 `action_decision` 호출로 교체.
- `app/llm/mock_rules.py`, `app/llm/prompts.py` — `action_decision` task 추가.
- `app/agents/question_strategy.py` — `build_value_question`은 폴백으로 보존; `should_value_clarify`는 제거 또는 미사용.
- (보존) `motivation.py::next_probe`는 폴백/참조로 둠 — 차원→질문 시드로 재사용 가능.

## 10. 테스트 계획 (TDD)

1. **mock action_decision 계약**: 발화에 "바로 추천해줘" → `action=="recommend"`. (RED: task 없음.)
2. **명시적 추천 존중 (end-to-end)**: category=None 자유대화에서 "바로 추천해주세요" → 추천이 나온다(무한 clarify 종료). ← 원래 버그의 회귀 가드.
3. **probe 차원이 12 vocab**: clarify일 때 dimension ∈ 가치5+동기7.
4. **구조 가드 보존**: 충돌 존재 → show_conflict; accept+추천이력 → close (기존 acceptance 테스트 유지).
5. 전체 스위트 그린(스마트워치 데모 포함).

## 11. 위험 & 오픈

- §36 hedging은 질문 저작에도 적용(프롬프트 계약). 약한 모델(deepseek) 대비 폴백 필수.
- critical-path 지연 1콜 — 측정 후 필요 시 병합.
- "동기↔가치 관계 측정" 방법(분석 단계)은 본 설계 범위 밖(별도).

## 12. 범위 밖

- 칩 편집 시 LLM 재질의, 동기↔가치 관계의 정량 검증 설계, 기존 프롬프트 긍정형 일괄 정리(별도 제안).
