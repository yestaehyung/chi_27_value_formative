# ValueCommit 연구 프레이밍 (HCI 관점)

**작성일:** 2026-06-08
**목적:** 이 시스템이 가지는 HCI 연구적 의미, 이 웹앱으로 수행 가능한 실험,
측정 가능한 구성개념, 한계를 정리한다. CHI류 full paper 설계의 출발점.

관련 문서: `../../ValueCommit_Theoretical_Module_Upgrade_Spec.md`(이론모듈),
`../../ValueCommit_Theoretical_Rationale_Note.md`(rationale),
`pscon-analysis.md`(데이터 분석), `algorithm-audit.md`(휴리스틱 감사)

---

## 1. 한 문장 정의

> 이 연구는 "AI가 사용자 의도를 더 정확히 추론하는가"를 묻지 않고,
> **"사용자가 자기 의도가 형성·해석되는 과정에 개입할 수 있을 때 어떤 가치가
> 생기는가"**를 묻는다. 그리고 그 질문에 답할 수 있는 측정 도구(Latent Yield,
> correction trace, value trajectory)를 갖춘 실험 플랫폼을 만든 것이다.

---

## 2. HCI적 의미 (핵심 기여)

핵심 기여는 추천 정확도가 아니라 **해석의 협상 가능성(negotiable interpretation)**.

### 2.1 발화만으로는 hidden intention이 나오지 않는다 (실증)

- PSCon 원대화 explicitness 100% explicit (사전검증 18개 대화)
- 우리 측정: 발화 경로 implicit/latent 3% vs 피드백 경로 21% (구조적 explicitness 기준)
- 시뮬레이션 4종: 발화만이면 Latent Yield 0.0 → trade-off+피드백으로 0.31~0.5

→ hidden intention은 "추출"하는 정보가 아니라 자극-반응으로 **창발시키는(elicit)**
상태. Suchman의 *situated action*, 의도를 상호작용 속에서 형성되는 것으로 보는
HCI 전통과 직결.

### 2.2 측정 타당도 → 협상된 타당도(negotiated validity)로 문제 치환

"LLM이 사용자 심리를 정확히 맞췄나?"는 검증 불가능한 측정 문제다. 이를
"사용자가 시스템 추론을 보고, 틀린 걸 고치고, 우선순위를 바꿀 수 있나?"라는
**상호작용 설계 문제**로 치환. SemanticCommit(UIST'25) 차용이 기능 이식이
아니라 인식론적 입장인 이유.

### 2.3 양방향 alignment + reflective HCI

보통 alignment 연구는 "AI를 사람에게 맞춤"이지만, conflict card + correction은
사용자도 자기 기준을 **스스로 articulate**하게 만든다 (hedonic_drifting persona가
대화 중 기준이 바뀌듯). 도구가 self-reflection을 유발하는 reflective HCI 측면.

---

## 3. 연구 질문 (RQ)

| RQ | 질문 | 대응 실험 |
|---|---|---|
| RQ1 Emergence | 발화·상품반응·chosen-rejected 피드백은 어떤 value-grounded hidden intention을 드러내는가? | A, C |
| RQ2 Representation | hidden intention을 theory-grounded·evidence-traceable·stakeholder-translatable ontology로 표현 가능한가? | A, E |
| RQ3 Correction | 사용자가 해석을 확인·수정할 수 있을 때 이해도·통제감·결정확신·alignment가 향상되는가? | **B** |
| RQ4 Discovery | chosen-rejected pair 기반 bottom-up feature가 top-down ontology가 놓친 차원을 발견하는가? | D |
| RQ5 Elicitation | 진단 trade-off·가치 질문이 hidden intention 산출(Latent Yield)을 높이는가? | **C** |

---

## 4. 수행 가능한 실험

데모에 이미 구현된 장치: study condition 3종, correction 로그(turn 시점),
Latent Yield 지표, value trajectory, persona×scenario 시뮬레이션, SME 뷰,
JSONL export, custom(회상 인터뷰) 시나리오.

### 실험 A — Formative Study (FS1) · 도구 완비

- 방법: 회상 인터뷰 맥락으로 custom 세션 → think-aloud → 사후 인터뷰
- 측정: 사용자가 **어느 시점에** 추론을 보고/수정하고 싶어하는지 (correction 로그
  turn-level 시점), transparency/correctability needs
- 산출: PSCon 1차 온톨로지가 못 잡은 element/관계 발굴 (이론모듈 §S58)
- N≈10, 세션 1.5~2시간

### 실험 B — Correctability의 효과 (중심 실험, between-subjects)

- 조건: `baseline`(추천만) / `explanation_only`(칩 표시, 수정 불가) /
  `correctable`(칩 수정 + conflict card + evidence drawer)
- 종속변수: 추천 이해도, **지각된 통제감(perceived control)**, value alignment,
  결정 확신, **인지부하(cognitive load)**
- 가설: correctable에서 통제감·alignment↑, 단 인지부하도↑ → trade-off 곡선
- 분석: 조건 간 ANOVA + correction 행동 로그와 자기보고 상관
- 이 실험이 CHI full paper의 중심.

### 실험 C — Elicitation 전략의 효과

- 조작: 진단 trade-off(불확실 anchor 검증 후보) + 가치 수준 질문 ON vs OFF
- 종속변수: **Latent Yield** (implicit/latent 비율 × 사용자 확인율),
  reflective value("내가 몰랐던 내 기준을 알게 됨")
- 시뮬레이션 사전결과: OFF=0.0 → ON=0.31~0.5 (persona별 변별). 사람 대상 검증.

### 실험 D — User Agent 시뮬레이션 (대규모 사전탐색)

- persona × scenario 수백 조합 자동 생성 → 사람 study 전에 conflict 빈발 조건,
  latent 다산 persona 사전 매핑
- 특이형 persona(self_contradicting, over_specific 등)로 conflict detection·
  correction UI stress test
- 위치: 사람 실험의 가설을 좁히는 도구 (그 자체가 결과는 아님)

### 실험 E — Stakeholder Study (FS2, SME)

- `/research/sme` 뷰를 SME에게 제시 → "이 집계 insight를 받으면 무엇을 알고
  싶고 어떤 행동을 할 것인가" 인터뷰
- 검증: 같은 온톨로지의 소비자/연구자/SME 3중 번역 가능성(stakeholder-translatability)
- N≈3~4, 30~45분, online 가능

---

## 5. 측정 가능한 구성개념

데모가 자동 로깅 → 바로 분석 가능.

**행동 지표 (로그 자동 수집)**
- Latent Yield = implicit/latent 비율 × 사용자 확인율 (`/api/research/metrics/latent-yield`)
- correction 빈도·시점(turn)·방향 (`correction_events`)
- conflict 해결 선택 분포 (accept_new / keep_old / merge / manual)
- chosen-rejected pair, productDiff, inferred hidden reason
- turns-to-stable-preference-state, value trajectory(stage별 anchor 이동)

**자기보고 지표 (실험 후 설문)**
- perceived control, transparency, value alignment, decision confidence,
  reflective insight, cognitive load
- 사전: Hedonic/Utilitarian Shopping Value scale로 그룹화

**궤적 지표**
- value trajectory의 hedonic↔utilitarian 이동이 만족도와 상관되는지

---

## 6. 정직한 한계 (논문에 명시)

1. 6축·ValueScore 가중치는 **서열만 정당화** — 사람 데이터로 보정 필요
   (절대값 민감도 분석 미수행).
2. 현재 검증은 **시뮬레이션** — 사람 study가 본 증거. 시뮬레이션은 가설 탐색용.
3. mock 상품 12종 → 네이버 실데이터(product_info 등) 연동 시 일반화 확인 필요.
4. correction을 *할 수 있는 것*과 *하고 싶어하는 것*은 다름 — FS1이 후자를 답해야 함.
5. explicitness는 LLM 자기라벨 대신 **출처 기반 구조적 정의**로 전환했으나
   (§2.2 이론 정의에 부합), 이 조작화가 사람 코더 판단과 일치하는지 검증 필요.
6. PSCon은 거래형 대화라 implicit이 거의 없음 — 본 시스템의 elicitation 효과를
   보려면 실제 쇼핑 맥락(FS1)이나 시뮬레이션이 필요(이것이 곧 연구 동기).

---

## 7. 시장 간 함의 (PSCon EN/CN 분석)

- EN: Clarify 주도(질문-응답 협업형, Clarify 42%)
- CN: 추천→거절+이유 반복형(40% 세션 "换一个", 거절에 太丑/太贵/质量太差 이유 동반)

→ 두 elicitation 모드(질문형/피드백형)가 모두 필요. 본 데모는 둘 다 구현
(가치 질문 + chosen-rejected 피드백). 한국 시장이 어느 모드에 가까운지가
FS1의 관찰 포인트 — 네이버 협업의 실용적 기여점.

---

## 8. 기여 요약 (CHI contribution statement 초안)

1. **개념적**: hidden intention을 협상되는 해석 상태로 재정의 + 협상된 타당도 프레임
2. **시스템적**: top-down 이론 ontology + bottom-up pair discovery + HITL correction을
   결합한 hybrid ontology 작동 시스템 (lifecycle/provenance/version 관리)
3. **방법적**: Latent Yield 등 hidden intention 산출을 측정하는 행동 지표 + 이를
   장착한 실험 플랫폼 (study condition·correction trace·trajectory 자동 로깅)
4. **실증적**: 발화 분석(0% latent) vs 자극-반응(31~50% latent)의 격차를 데이터로
   제시 — "발화만으론 부족하다"는 가설의 정량 근거
