# 알고리즘 휴리스틱 감사 노트 (2026-06-05)

데모 코드의 "임의로 정한" 알고리즘/상수를 전수 점검한 결과.
각 항목: **위치 / 내용 / 판정(수정·문서화·유지) / 근거**.

## 이번에 수정한 것

| # | 위치 | 기존 문제 | 수정 |
|---|---|---|---|
| 1 | `ontology/merge.py::_similar` | 공백 토큰 Jaccard(0.6) — 한국어에서 조사 변형("가격이 낮을수록 좋음" vs "가격이 낮은 게 좋음")을 다른 topic으로 판정 → 중복 topic 양산 위험 | **문자 bigram Jaccard(≥0.55) + 정규화 포함관계**로 교체. 한국어 띄어쓰기에 무관 |
| 2 | `products/scoring.py` finalScore의 `0.05 * 0.5` | diversityScore가 상수 0.5로 박혀 있어 사실상 죽은 항 | `search.apply_diversity_rerank` 신설 — **MMR식 greedy**: 이미 뽑힌 후보와 브랜드 중복 −0.03, trade-off 버킷 중복 −0.02 (합계가 spec §14.2의 0.05 가중치 한도) |
| 3 | `scoring.py` 예산 파싱 | `(\d+)만원`만 인식 — "20만 원", "200000원", "3십만원" 미인식 | `parse_budget_won()` 신설: 십만원/만원/원(4자리+, 콤마 허용) 지원. mock 규칙·constraint 매처 공용 |
| 4 | `scoring.py::text_relevance` | 공백 토큰 부분일치만 — 한국어 조사 붙은 쿼리("스마트워치를")가 매칭 실패 가능 | 문자 bigram 겹침 점수(×0.85)와 토큰 점수의 max로 보강 |
| 5 | `products/cue_extractor.py` priceCue | 절대 금액 경계(5/10/18/50만) — 카테고리 무관이라 노트북 40만원이 "high" | **카테고리 내 분위수(20/40/60/80%)** 기반으로 변경, 데이터 부족 시 절대 금액 폴백. seed_loader가 카테고리별 가격 분포 전달 |

## 문서화로 충분 (의도된 설계, 상수 근거 명시)

| 위치 | 상수 | 근거 |
|---|---|---|
| `scoring.py` finalScore 가중치 (0.30/0.20/0.15/0.15/0.10/0.05/0.05) | 코딩 명세서 §14.2에 정의된 값 — 임의 아님 | spec |
| `state_builder.py` PRIORITY_WEIGHT(0.35/0.6/0.85/1.0), STRENGTH(0.45/0.75/1.0), IMPACT(0.55/0.8/1.0), TEMPORAL(0.9/1.0/0.5/0.3), CORRECTION(1.0/0.85/0.65), conflict_penalty 0.7 | 이론모듈 §12.2-12.3의 ValueScore 구성요소를 단조 척도로 구현. **절대값 자체가 아니라 순서 관계(서열)가 이론적 주장** — 민감도 분석은 향후 과제로 명시 | 이론모듈 |
| `state_builder.py` noisy-OR 결합 | 합산은 topic 수에 따라 발산, max는 다중 근거를 무시 — noisy-OR은 "독립 근거의 누적 확신" 의미론과 일치 | 설계 선택 |
| `state_builder.py` stability = 0.7+0.1×evidence수(cap 1.0) | evidence 1개=0.8, 3개=1.0 — 빈도 기반 안정성의 선형 근사 | 이론모듈 §12.2 Stability |
| contribution 노출 컷오프 0.03 | UI 분해 표시용 노이즈 컷 — 점수 계산에는 영향 없음 | UI 전용 |
| `search.py::assign_bucket` 판정 순서 | 디자인/선물패키지 → 저가·인기 → 신뢰·장기 → … 순서가 seed 카탈로그를 버킷에 고르게 분산시키도록 조정됨 (§14.3 trade-off 노출 목적). 순서 자체가 로직임을 주석으로 명시 | spec §14.3 |
| `cue_extractor.py` trust/popularity/seller 경계 | ltr≥0.3·rating≥4.6=high 등 — mock 카탈로그 스케일 기준. 실데이터 연동 시 분위수화 필요(가격과 동일 방식) — TODO로 명시 | mock 한정 |
| `evaluation/value_profile.py` USER_TYPE_RULES 가중치 | anchor→유형 선형 결합 + topic 키워드 부스트(0.12) — **분석 lens일 뿐 판정이 아님**(이론모듈 §5.3.4 "고정 label이 아니라 lens"). FS1에서 사전설문(H/U scale)과의 상관으로 보정 예정 | 이론모듈 |
| `agents/user_agent.py` 반응 규칙 (social≥0.7, 가격>20만 등) | ground truth 시나리오의 productCueTriggers를 구현한 것 — 임의가 아니라 시뮬레이션 통제 변수 | 설계 |
| `wimhf` featureScore = 0.4·coverage + 0.3·consistency + 0.2·novelty + 0.1·interpretability | 코딩 명세서 §11 Phase D 공식 | spec |
| conflict_detector 기본 해결옵션 폴백 (valid<3 → 표준 4종) | LLM 출력 품질 안전망 — 옵션 부재로 카드가 죽는 것 방지 | 견고성 |
| `merge.py` 신뢰도 병합 `min(0.98, max(old,new)+0.05)` | 같은 기준의 반복 evidence는 확신을 올리되 1.0(사용자 확인 전용)은 예약 | 이론모듈 §17.2 confirmed 의미론 |
| `levels.py` CAUSAL_EVIDENCE 3레벨 + CAUSAL_ACCEPT_LEVELS=(stated_cause,) | 인과(MOTIVATES/REFINES) 엣지의 증거 수준 범주(M1). 인과 인정 규칙이 해석 가능해짐: "사용자가 직접 언어화한 인과만 통과". 캐시값 0.95/0.75/0.5는 서열만 주장. **judge 평결 vs 사람 주석 표본(N≥100, κ)으로 검증 필요** (measurement M5) | 측정 설계 M1/M5 |
| `levels.py` derive_anchor_score (confirmed/inferred/weak × strength × impact 곱) | anchor score를 LLM 스칼라 대신 범주 3종에서 결정론 산출 (OQ2 = derive-from-triple로 결정). 절대값이 아니라 세 축 단조성만 주장 — 결정 층 효용 캐시 | 측정 설계 M1/M2 |
| `levels.py` CONFIDENCE/MOTIVATION 레벨 캐시값 (0.85/0.6/0.35, 0.8/0.5/0.3) | 범주가 원본, 숫자는 정렬·probe 선택용 파생 캐시. covered_dims 임계 0.4와의 관계: hints(0.3)는 probe를 막지 못함(약한 힌트로는 질문 생략 안 함) | 측정 설계 M1/M2 |
| `motivation.py` M4 승격 규칙 — suggests 이상 독립 신호 2개 → asserts 등가 | noisy-OR 대체. '2'는 미보정 이산 상수 — FS1 사전설문(H/U scale) 상관으로 보정 예정 | 미보정·검증 경로 있음 |
| `merge.py` explicitness 노드 캐시 규칙 (explicit 엣지 1개 ≥ → explicit; 전부 latent → latent; else implicit) | hidden의 엣지 기반 정의(graph design D1)의 노드 수준 투영 — "어디서든 한 번 직접 말했으면 explicit". Latent Yield v2가 같은 규칙 사용 | graph design D1 |
| `prompts.py` kind 4종 분류 (constraint/context/avoidance/preference) | **이론 도출이 아닌 공학 분류** — 프롬프트에 정의 블록으로 격리(교체 가능). FS1에서 실사용자 의도가 4종에 안 맞는 사례가 쌓이면 개정 | 플래그됨 (FS1 검증 대상) |

## 알려진 한계 (향후 과제)

1. **ValueScore 가중치 민감도 분석 미수행** — 서열만 보장됨. FS1 데이터로 anchor 점수 vs 사용자 자가보고 상관 검증 필요.
2. trust/popularity cue 경계는 실데이터(네이버 product_info) 연동 시 분위수 재계산 필요.
3. `_similar` bigram 0.55 임계값은 시드 라벨 쌍 검증 기준 — 실사용 topic 라벨로 PR-curve 점검 권장.
4. action_selector는 규칙 기반 — 정보 충분성 판단 기반 적응형 질문(주간덱 S3)은 별도 과제.
