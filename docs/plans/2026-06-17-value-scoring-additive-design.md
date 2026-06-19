# Value Scoring: 곱셈+noisy-OR → 가산형(가중 평균) 전환 설계

> 작성 2026-06-17. 상태: **결정됨, 구현 중.** 이 문서는 나중에 수정 가능하도록 결정과 근거·미결 항목을 함께 남긴다.
> 대상 코드: `app/ontology/state_builder.py::compute_anchor_scores` (가치 5축 radar/스냅샷 점수).

## 1. 문제

현재 ValueScore(이론모듈 §12.3)는 한 의도(topic)의 기여를 **여러 [0,1] 요소의 곱**으로 만들고, anchor별로 **noisy-OR**로 합친다:

```
contribution = intensity × evidence_strength × decision_impact × temporal
             × recency × correction × stability × priority × conflict_penalty
score(anchor) = 1 − ∏(1 − contribution)        # noisy-OR
```

문제점:
- **이론 근거 없음.** TCV(Sheth·Newman·Gross 1991)는 가치들이 **독립적·가산적**으로 선택에 기여한다고 말한다. 곱셈 체인+noisy-OR은 TCV가 아니라 우리 엔지니어링 구성물이다.
- **해석 불가·신뢰 저하.** [0,1] 여러 개를 곱하면 점수가 급격히 작아지고(0.6×0.85×… ≈ 0.3) "이 축이 왜 이 값인지"가 안 보인다.
- **측정 요소와 가치 요소가 섞임.** confidence/recency/stability/correction/conflict는 *증거 신뢰도/동역학*이지 *가치*가 아닌데 가치 신호(intensity)와 같은 층에서 곱해진다.

## 2. 결정

1. **범주형(M1) 유지.** LLM은 숫자를 내지 않는다 — confidence/evidenceStrength/decisionImpact/priority 등 **범주 + 인용(quote)**만 내고, 코드가 숫자로 변환한다. (생짜 LLM 스칼라는 식에 0개. `anchor_mapper`는 이미 `derive_anchor_score(범주)`로 intensity 산출, LLM score 무시.)
2. **결합을 곱셈+noisy-OR → 가산형(가중 평균)으로 교체.**

## 3. 이론 근거 (가산형)

소비자 가치/태도 이론은 결합을 **합**으로 한다:
- **기대-가치 모델(Fishbein-Ajzen):** 태도 = Σ(믿음ᵢ × 평가ᵢ)
- **다속성효용(MAUT/WADD):** 효용 = Σ(중요도ⱼ × 값ⱼ), 보상적
- **TCV:** 5가치 독립 + 가산 기여 → anchor마다 *따로* 합산

공통: "값 × 중요도"의 **합**. 곱이 아니다.

## 4. 신뢰 분석 (왜 범주형 유지)

- LLM "confidence 직접 출력"(verbalized confidence) 연구는 존재하나, 결론은 **과신(overconfident)·정오답 변별력 약함** — 생짜로는 못 믿음.
  - Xiong et al., *Can LLMs Express Their Uncertainty?* ICLR 2024 (arXiv:2306.13063)
  - 캘리브레이션 route: ConfTuner (NeurIPS 2025), Learning to Generate Verbalized Confidences (NeurIPS 2024) — **데이터 보정 필요**
- LLM-as-judge/annotation 관행: **범주/이진이 미세 숫자보다 안정·재현성↑**, 검증은 **Cohen's κ / weighted κ**로 사람 라벨 대비.
- → 우리 범주형(→코드 숫자)이 문헌상 더 안전. confidence를 숫자로 내려면 *캘리브레이션 + κ 검증* 필수(FS1 이후).

## 5. 새 공식 (lean 가산형)

anchor a마다 (독립):

```
active = topics 중 temporal_status ≠ 'resolved' 그리고 open conflict 아님   # 활성 의도 선택
weight(t) = PRIORITY_WEIGHT[t.priority] × t.confidence                      # 중요도 × 확신
intensity(t→a) = m.score   # 범주(confidence×evidenceStrength×decisionImpact)에서 파생, LLM 숫자 아님
score(a)     = Σ_active weight×intensity / Σ_active weight                   # 가중 평균 ∈ [0,1]
confirmed(a) = 같은 식, m.confidence=='confirmed' 인 매핑만                   # 내부 다각형(확인)
```

**워크드 예시 (Functional):**

| 의도 | intensity | priority | confidence | weight | weight×intensity |
|---|---|---|---|---|---|
| "튼튼한 거" | 0.8 | 0.85 | 0.85 | 0.72 | 0.58 |
| "가성비" | 0.6 | 0.6 | 0.6 | 0.36 | 0.22 |

score(Functional) = (0.58+0.22) / (0.72+0.36) = 0.80/1.08 ≈ **0.74** — 그리고 "튼튼한 거"가 더 기여한 게 보임.

## 6. 무엇이 바뀌나 / 유지되나

**바뀜**
- 곱셈 체인 → `weight = priority × confidence`만 (곱은 *가중치 형성*에만, 가치 결합은 합)
- noisy-OR → **가중 평균**
- recency/stability/correction/temporal/conflict_penalty 의 *연속 곱* 제거 → **활성 선택**으로 대체(resolved·open-conflict 제외)
- evidence_strength·decision_impact 는 이미 intensity(`derive_anchor_score`) 안에 흡수돼 있으므로 식에서 중복 제거

**유지**
- 범주형 입력 + 인용 강제(M1), LLM 숫자 미사용
- confirmed vs total 두 점수(내부/외부 다각형) → 불확실성 = 가치 질문 트리거
- anchor 독립 계산, 빈 결과 폴백

## 7. 미결/향후 (revisable)

- **judge agent (M5)** — 빌더의 범주 분류를 독립 모델이 감사. **넣을지 검토 중.** κ 검증과 직접 연결.
- **상수 보정** — PRIORITY_WEIGHT / CONFIDENCE 값은 여전히 손으로 정함. **서열만 주장**, FS1 데이터로 보정 + 민감도 분석 예정.
- **sum vs average** — 현재 *가중 평균*(레벨·해석 쉬움). "근거 많을수록 ↑"를 원하면 가중 합(정규화)로 전환 가능.
- **weakened 처리** — 현재 active로 포함(=down-weight 제거). 필요시 선택 계층으로 재도입.
- **verbalized confidence + 캘리브레이션** — FS1 데이터 쌓이면 대안으로 실험.

## 8. 검증

- 백엔드 테스트(mock) 유지 (watch_* 데모). anchor_scores 절대값은 바뀌지만 **서열/동작**이 깨지지 않는지 확인.
- 동일 입력에서 점수가 [0,1]·해석 가능(기여자 분해 유지)인지 확인.

## References
- Sheth, Newman, Gross (1991), *Why we buy what we buy: A theory of consumption values.*
- Fishbein & Ajzen — expectancy-value model.
- Keeney & Raiffa — MAUT / weighted additive.
- Xiong et al. (ICLR 2024) arXiv:2306.13063; ConfTuner (NeurIPS 2025); Learning to Generate Verbalized Confidences (NeurIPS 2024).
