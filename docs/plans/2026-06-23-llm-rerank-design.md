# LLM 기반 가치·동기 Reranking 설계

**날짜:** 2026-06-23
**상태:** 설계 → 구현
**범위:** 추천 랭킹을 임의 점수공식(trust/popularity) → LLM rerank(사용자 가치·동기 기반)로 전환

---

## 1. 문제

추천 랭킹이 사용자 의도(가치·동기)를 제대로 반영 못 함:
- 점수공식의 trust(0.10)/popularity(0.05)는 **TCV5·동기 어디에도 근거 없는 일반 커머스 상수** (이론기반 원칙 위배). 실제로 "클래식 울코트" 요청에 인기 많은 나이키 바람막이를 1위로 올림.
- 예산은 점수항(0.20)으로 **필터와 중복**(통과품은 다 1.0, 죽은 항). 비보완적 스크리닝(Payne/Bettman/Johnson) 위반.
- 임베딩 유사도만으론 "가성비=싸야 함" 같은 추론 못 함 → "가성비" 요청에 에어팟.

→ 이미 trust/popularity/예산항은 제거함(2026-06-23). 남은 근본 해결: **랭킹을 LLM이 가치·동기로 판단.**

## 2. 근거 (선행 연구)

- **주 프레임워크: LLM4Rerank (WWW'25, ACM Web Conference)** — "Goal" 문장으로 어느 기준을 우선할지 LLM이 판단해 listwise rerank. 우리 차별점: 그들의 Goal은 *수동 입력*, **우리 Goal은 대화에서 추출한 가치·동기(자동)**.
- 보조: LLMRank(ECIR'24) — 위치·인기 편향 발견 및 프롬프트 완화 교훈. Pairwise Ranking Prompting(NAACL'24) — LLM 랭킹 유효성.
- retrieve-then-rerank 2단계는 IR 표준.

## 3. 핵심 결정

- **D1.** retrieve(임베딩)로 후보 추리고, **최종 순위는 LLM rerank**가 결정 (scoring 마법공식 대체). 단일 listwise rerank.
- **D2.** rerank의 "Goal" = 추출된 **사용자 의도**: 시나리오 맥락 + 토픽(label/description/사용자 인용) + 가치(TCV5)·동기(7) raw 점수. **점수→자연어 하드코딩 변환 안 함** — 사용자가 실제 한 말·토픽 설명을 그대로 주고 LLM이 판단.
- **D3.** 동기→가치 **위계를 프롬프트로 명시**(단계 분리 X). 이론상 동기(활동층위)가 가치(선택층위)를 조건짓지만, 충돌이 아니라 위계라 단일 rerank로 충분(YAGNI). LLM4Rerank의 다중 노드 순회는 우리 규모(후보 15)엔 과함.
- **D4.** rerank 후보 = 상위 **15개** (위치편향·토큰 vs 누락 균형. 카테고리 풀 50의 30%). 조정 가능.
- **D5.** rerank가 **card_rationale 흡수** — 순위 + 각 reason/matched/weak을 한 호출로 (호출 0개 추가, 일관성).
- **D6.** 편향 완화 프롬프트 가드: 인기편향("유명·리뷰많음 자체로 올리지 마라"), 위치편향("입력 순서는 임베딩순일 뿐 정답아님"), 사실가드, 가치우선.

## 4. 파이프라인

```
search_products():
  1. 임베딩 retrieve (200, 코사인 점수 포함)        [기존]
  2. 카테고리·예산·태그·이미지 필터               [기존]
  3. 임베딩 점수순 정렬 → 상위 15 추림            [scoring 축소: 1차 컷용]
  4. ★ LLM rerank (15개, 가치·동기 Goal) ★        [신규]
  5. trade-off 다양성으로 3개 선정               [기존]
```

## 5. 코드 구조

- **prompts.py**: `rerank` task. SYSTEM(동기→가치 위계 + 편향 가드), FORMAT(출력 스키마).
- **mock_rules.py**: `rerank` 핸들러 — 입력 순서 유지(결정론, 테스트 안전).
- **response_generator.py**: `rerank_by_intent(provider, candidates, intent_ctx)` 신규. 순위 + 카드텍스트 반환. 폴백=입력순서.
- **service_agent.py**: search 후 rerank 호출, 결과로 impressions 생성. card_rationale 호출 제거(rerank가 흡수).
- **search.py**: 상위 15 추려 넘기는 지점 + rerank 결과로 최종 정렬.

### rerank 입력(Goal)
```
시나리오: "운동 좋아하는 친구 선물용 무선이어폰"
최근 발화: [사용자가 한 말 몇 개]
추출 기준(토픽): [{label, description, 사용자인용}]
가치(TCV5, 참고): {Functional: 0.9, ...}  # raw, 변환 안 함
동기(7, 참고): {BargainValue: 0.8, ...}
위계 지시: "동기가 가치를 조건짓는다 — 이 쇼핑 목적 맥락에서 가치 기준에 맞게 정렬"
후보: [{index, 제목, 가격, 평점, 리뷰수, 한달리뷰, 설명, 가격대}] ×15
```
### 출력
```json
{"ranking":[{"index":7,"reason":"...","matched":["..."],"weak":["..."]}, ...]}
```

## 6. 폴백 (재현성)
- mock provider → rerank 스킵, 임베딩 순서. mock 24개 안전.
- LLM 실패/파싱오류 → 임베딩 순서. index 누락 → 누락분 임베딩 순서로 뒤에.

## 7. 안 하는 것 (YAGNI)
- 다중 aspect 노드 CoT 순회 (LLM4Rerank 원형) — 우리 규모·위계 구조엔 과함
- 점수→자연어 하드코딩 변환
- 가치/동기 2단계 분리 rerank
- trust/popularity 부활

## 8. 검증
- mock 24개 통과
- "클래식 울코트"→울코트 1위, "가성비"→저가, "RGB게이밍"→게이밍 (가치 반영 확인)
- rerank 전후 순서 로깅(편향 추적), reason 저장(연구 분석)
