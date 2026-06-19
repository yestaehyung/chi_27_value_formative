# PSCon 데이터 분석 노트 (2026-06-05)

EN 826 / CN 904 대화 전수 분석 + 실대화 파이프라인 사전검증 결과.
원시 통계: `backend/seed/pscon_stats.json`, 사전검증 원자료: `docs/pscon_prevalidation_results.json`

---

## 1. EN 시장 분석 (826 대화)

| 항목 | 결과 |
|---|---|
| user intent | Interpret 57% > Reveal 32% > Chitchat 8% > Revise 2% > Inquire 0.5% |
| system action | Recommend 56% / **Clarify 42%** |
| Clarify 상위 속성 | **Brand 468** > Price 392 > Departments 104 > Type 91 > Reviews 26 |
| 대화 길이 | 중앙값 4턴 (최대 8) |
| 시나리오 신호 | 브랜드 14% > 품질/신뢰 13% > 예산 6% > 상황 4% > 선물 2% |

## 2. CN 시장 분석 (904 대화)

| 항목 | 결과 |
|---|---|
| user intent | Interpret 52% > Reveal 32% > Chitchat 9% > **Revise 7%** > Inquire 0.03% |
| system action | **Recommend 79% / Clarify 14%** |
| 대화 길이 | 중앙값 3턴 |
| 특징 신호 | **재추천 요청(换一个/别的) 40%** — "这个太丑了吧，换一个好看的" |

## 3. 시장 간 비교 — 두 가지 elicitation 모드

| | EN | CN |
|---|---|---|
| Clarify 비중 | 42% | 14% |
| Revise intent | 2% | 7% |
| 반복 방식 | 질문→응답 (협업형) | 추천→거절+이유→재추천 (피드백형) |

> **핵심 발견:** CN의 거절 발화는 이유를 동반한다 (太丑=디자인, 太贵=가격,
> 质量太差=품질) — 사실상 **dislike + reason_code**다. 본 데모의
> chosen-rejected 피드백 패러다임이 CN 시장 행동을, 적응형 질문이 EN 시장
> 행동을 각각 커버한다. **질문형/피드백형 두 elicitation 모드가 모두
> 필요하다는 시장 간 실증.** (네이버 협업 맥락: 한국 시장이 어느 모드에
> 가까운지가 formative study의 관찰 포인트가 될 수 있음)

## 4. 실대화 파이프라인 사전검증 (포럼 파이프라인 1단계)

층화 표본 18개 대화(gift/budget/brand/quality/explore/replace/situation)를
topic 추출 + 6-anchor 매핑(gpt-4o-mini)에 통과시킨 결과:

| 지표 | 결과 |
|---|---|
| ≥1 topic 추출된 대화 | **18/18 (100%)** |
| topic 수 | 35개 (대화당 1.94) |
| evidence trace rate | **1.00** (모든 topic이 실제 turn id 참조) |
| 기준성(criterion-like) | **1.00** (상품명 나열이 아닌 선택 기준 형태) |
| anchor 분포 | Functional 20 > Epistemic 6 = Conditional 6 = Affective 6 > Social 4 = Hedonic 4 |
| explicitness | **explicit 100%** |

추출 품질 예시:
- "브랜드를 잘 몰라 실패 확률이 낮은 선택을 원함" → Epistemic 0.8
- "여성에게 어울리는 디자인을 원함" → Conditional 0.9, Social 0.7
- "예산은 $2000로 설정됨" → Functional 0.9

### 해석과 한계 (중요)

1. **추론 가능성 검증 통과** — 기존 CRS 벤치마크 대화에서도 evidence-traceable한
   기준 추출이 안정적으로 동작한다 (포럼 덱 "사전 검증" 단계 충족).
2. **그러나 explicitness가 100% explicit** — PSCon 대화는 표면 조건 위주의
   거래형 대화라 implicit/latent hidden intention이 드러나지 않는다.
   Functional 편중(20/46 매핑)도 같은 원인.
3. → 이것이 바로 주간덱 S5의 주장("기존 데이터셋은 사용자 유형/특성 고려가
   안 되어 한계")의 **실증 근거**다. implicit/latent 차원을 보려면
   (a) trade-off 후보 제시 + 피드백 수집(본 데모), (b) ground-truth persona
   시뮬레이션, (c) formative study가 필요하다. 사전검증은 파이프라인의
   *가능성*을 입증했고, 벤치마크의 *한계*를 정량화했다.

## 5. 재현 방법

```bash
cd valuecommit/backend
.venv/bin/python scripts/pscon_prevalidation.py   # 사전검증 (LLM 호출 ~36회)
```
EN/CN 분포 분석 스크립트는 일회성으로 실행됨 — 통계는 `seed/pscon_stats.json`에 고정.
