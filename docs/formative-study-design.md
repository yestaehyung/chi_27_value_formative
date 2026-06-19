# Formative Study Design (FS1)

**작성일:** 2026-06-08
**성격:** 탐색적(exploratory) · 질적 중심 · 가설 생성 단계
관련: `research-framing.md`(실험 A), `pscon-analysis.md`, 이론모듈 §S56-60

> ⚠️ 이 study는 **에이전트의 성능을 평가하는 단계가 아니다.** 사용자가 쇼핑
> 에이전트에게 기대하는 *이해의 수준*, 자신을 잘 이해했다고 느끼는 *순간*,
> 의도와 어긋났다고 느끼는 *순간*을 발견하기 위한 단계다.
> (성능 비교는 후속 between-subjects 실험 B의 몫)

---

## 1. 목적과 탐색 질문

### 목적
대화형 쇼핑에서 (1) hidden intention이 실제로 어떻게 드러나는지, (2) 사용자가
에이전트의 해석을 언제 신뢰/불신하는지, (3) 사용자가 hidden intention을 어떤
방식으로 보고·수정하고 싶어 하는지를 탐색한다.

### 탐색 질문 (EQ — 검증이 아니라 발견)

| EQ | 질문 | 데모 계측 |
|---|---|---|
| EQ1 | 사용자가 명시적으로 말하지 않았지만 중요하게 고려한 hidden intention은 무엇인가? | 회상 인터뷰 발화 ↔ 시스템 추출 topic 대조 (source=feedback/latent) |
| EQ2 | 에이전트가 hidden intention을 외재화(칩/conflict card)했을 때 사용자는 이를 어떻게 받아들이는가? | think-aloud + chip 반응(confirm/reject/edit) 로그 |
| EQ3 | 사용자는 해석을 **언제·어떤 형태로** 확인·수정·거부하고 싶어 하는가? | correction_events(turn 시점·action·before/after) + think-aloud |
| EQ4 | 사용자가 에이전트를 **신뢰/불신하는 순간**은 언제인가? | think-aloud 발화 코딩 + evidence drawer 열람 시점 |
| EQ5 | 사용자가 기대하는 *이해의 수준*은 어디까지인가? (속성? 가치? 맥락?) | 사후 인터뷰 + 어떤 칩에 동의/거부했는지 |

---

## 1-b. Design Goals (시스템이 FS1을 가능하게 하려면)

탐색 질문을 관찰 가능하게 만들기 위해 **아티팩트가 충족해야 할 설계 목표**.
각 DG는 구현 산출물과 연결된다.

| DG | 설계 목표 | 무엇을 가능하게 하나 | 구현 산출물 | 상태 |
|---|---|---|---|---|
| DG1 Externalize | 추론한 hidden intention을 사용자가 검토 가능한 형태로 외재화 | EQ2 | chip · conflict card · evidence drawer | ✅ 기존 |
| DG2 Trace reactions | 사용자의 수용/거부/수정과 그 **시점(turn)**을 포착 | EQ3 | correction_events(시점·action·before/after) | ✅ 기존 |
| DG3 Inspect-logging | 사용자가 **언제 근거를 확인**하는지(불신·검증 신호) 포착 | EQ4 | evidence drawer 열람 이벤트 로깅 | ✅ 신규 |
| DG4 Moment-marking | 연구자가 **신뢰/불신/혼란 순간**을 turn에 고정해 기록 | EQ4 | 관찰 마커(study mode) + 타임라인 표시 | ✅ 신규 |
| DG5 Ground-truth gap | 회상 인터뷰 ground-truth와 시스템 KG의 **갭(놓침/오탐/신규발견)** 분석 | EQ1, EQ5 | ground-truth 입력 + gap 분석 뷰 | ✅ 신규 |
| DG6 Exportable trace | 모든 관찰 신호를 분석 가능하게 export | 분석 | JSONL(markers·inspections·corrections·gap) | ✅ 신규 |

---

## 2. 참가자

- N = 10명 내외 (포화까지 조정)
- 모집: 최근(2~4주 내) 기억에 남는 온라인 쇼핑 경험이 있는 사람
- 사전 그룹화: Hedonic/Utilitarian Shopping Value scale로 성향 분류
  (분석 시 lens로만 사용, 모집 쿼터 아님)
- 세션: 1.5~2시간, 대면 또는 화면공유

---

## 3. 조건 설정

- **단일 조건: `correctable`** (칩 수정 + conflict card + evidence drawer 전부 노출)
  - 이유: formative의 목적이 *수정 행동의 관찰*이므로 기능을 모두 열어둔다.
    조건 간 비교(baseline/explanation_only)는 실험 B에서.
- LLM provider: `openai`(gpt-4o-mini) — 실제 추론 변동성을 관찰
- 시나리오: **회상 인터뷰 기반 custom 시나리오** (각 참가자 고유)
  - 보조: 참가자가 회상할 경험이 약하면 고정 시나리오(선물/탐색/특정상황/고관여) 중 선택

---

## 4. 절차 (4단계)

### Step 1. 사전 설문 (10분)
- Hedonic/Utilitarian Shopping Value scale
- 최근 쇼핑 경험 회상 워밍업

### Step 2. 회상 인터뷰 (20~30분) — *hidden intention 표면화의 1차 자료*
- "최근 기억에 남는 쇼핑을 떠올려 주세요. 무엇을, 누구를 위해, 어떤 상황에서?"
- 핵심: **검색창/대화로 직접 표현하지 않았지만 중요하게 고려한 요소**를 끌어냄
  - "겉으로는 X라고 검색했지만, 사실 마음속으로 중요하게 본 건?"
  - MEC laddering 차용: "그게 왜 중요했어요?"를 3회 반복 (속성→결과→가치)
- 산출: 참가자별 **ground-truth hidden intention 리스트** (시스템 평가 기준선)
- 이 맥락을 데모의 **custom 시나리오 입력**으로 옮김

### Step 3. 대화형 에이전트 재현 + Think-aloud (40~50분) — *핵심 관찰*
- "당시와 비슷한 needs를 지금 다시 가지고 쇼핑한다면" 형태로 데모 사용
- think-aloud 진행. 진행자는 개입 최소, 단 아래 **순간 포착 프롬프트**만:
  - 추천이 떴을 때: "지금 이 추천 어떻게 느껴지세요?"
  - 칩이 떴을 때: "에이전트가 이렇게 이해했다는데, 맞아요?" (EQ2)
  - conflict card가 떴을 때: "이 질문 어떻게 느껴지세요?" (EQ3)
  - 사용자가 멈칫/불편 표시: "방금 무슨 생각 하셨어요?" (EQ4 신뢰/불신)
- 데모가 자동 기록: turn별 topic 생성, chip 반응, correction 시점/방향,
  conflict 해결 선택, evidence drawer 열람, Latent Yield

### Step 4. 사후 인터뷰 (20분) — *기대 수준과 갭 회상*
- "내가 원했던 것 vs 시스템이 잡아낸 것"의 갭 회상 (EQ1, EQ5)
- "추론 과정을 **보고 싶었던/수정하고 싶었던** 시점이 있었나요?" (EQ3)
- "어느 순간 '얘가 날 이해했다' 혹은 '전혀 모른다'고 느꼈나요?" (EQ4)
- 회상 인터뷰에서 나온 ground-truth 중 **시스템이 못 잡은 것** 함께 확인

---

## 5. 목적 ↔ 데모 계측 매핑

| 탐색 목적 | 데모가 자동 포착 | 인터뷰가 포착 |
|---|---|---|
| hidden intention이 어떻게 드러나는가 | source별 topic(발화 vs 피드백 vs 비교), Latent Yield, value trajectory | 회상 인터뷰의 미표현 요소, laddering 사다리 |
| 언제 신뢰/불신하는가 | evidence drawer 열람 시점, 추천 후 행동(수용/이탈) | think-aloud 신뢰/불신 발화, 사후 회상 |
| 어떻게 보고·수정하고 싶어 하는가 | correction_events(시점·action·before/after), conflict 해결 선택 분포 | "수정하고 싶었던 시점" 회상, 원하는 표현 형태 |

핵심: **자동 로그가 "무엇을·언제"를, 인터뷰가 "왜"를** 담당한다 (행동+이유 삼각측량).

---

## 6. 분석

- **질적**: think-aloud + 인터뷰 전사 → 신뢰/불신 *순간*의 thematic analysis,
  수정 욕구의 형태/시점 코딩
- **양적(기술통계, N 작아 추론통계 아님)**:
  - correction 시점 분포 (어느 turn/stage에서 수정이 몰리는가)
  - chip 반응 분포 (confirm vs reject vs edit 비율)
  - Latent Yield: 회상 인터뷰 ground-truth 대비 시스템이 표면화한 비율
  - source별 hidden intention 발현(발화 vs 자극-반응)
- **대조**: 회상 ground-truth ↔ 시스템 KG (놓친 것 / 잘못 잡은 것 / 새로 발견한 것)

---

## 7. 산출물 (다음 단계로 가는 입력)

1. **Ontology refinement**: PSCon 기반 1차 ontology가 못 잡은 element/관계/계층
   (실제 사용자 hidden intention으로 seed concept·relation 보강)
2. **Design implications**: 사용자가 hidden intention을 *언제·어떤 형태로* 보고/
   수정/확인하고 싶어 하는지 → transparency·correctability 설계 요구사항
3. **실험 B/C의 가설 정련**: 어떤 조건·순간에서 correction이 가치를 만드는지

---

## 8. FS2 (SME) — 병행

- N = 3~4명, 30~45분, online 가능
- 1차 ontology + `/research/sme` 뷰 mock-up 제시 → "이 데이터를 받으면 무엇을
  알고 싶고 어떤 행동을 할 것인가" 인터뷰
- 검증: stakeholder-translatability (같은 KG의 SME 번역 유용성)

---

## 9. 윤리·진행 주의

- 에이전트 추론을 **확정 사실처럼 제시하지 않음** (§36) — 참가자가 진단당하는
  느낌을 받지 않게. think-aloud에서 불편 신호 시 즉시 맥락 확인.
- 추론 노출이 오히려 답을 유도하지 않도록(demand characteristic) 진행자 멘트 표준화.
- 회상 인터뷰의 개인 쇼핑 경험은 민감 정보 가능 — 익명화·동의.
