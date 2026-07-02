# 3-에이전트 CRS 재설계 (2026-07-02)

대화 세션(추천 에이전트 분석 & 개선방향, 2026-07-01~02)에서 합의된 설계의 기록.
이전 설계 문서(2026-06-25 action-decision)를 계승·확장한다.

## 결정 요약

**아키텍처 = 3 에이전트 + 도구 1 + 렌더러 1.** "멀티 에이전트 vs 단일"은 잘못된 축 —
600상품 카탈로그는 컨텍스트에 못 넣고 LLM 파라메트릭 지식에도 없으므로(영화 도메인인
MACRS와 다름) `LLM(이해→쿼리) → [임베딩 검색] → LLM(선별)` 분할이 물리적으로 강제된다.
질문은 "이음새를 어디에 두느냐"이고, 이음새는 강제 이유가 있는 3곳뿐:

1. **임베딩 검색** (물리적 — 카탈로그는 도구로만 접근)
2. **Intent 추론 ↔ 서비스** (인식론적 — 가치 추론과 상품 선별을 한 호출에 두면
   모델이 고른 상품을 정당화하는 방향으로 가치를 역산(back-rationalize)해 연구 DV가 오염)
3. **LLM-first, write-last** (동시성 — 기존 규칙 유지)

```
사용자 발화
   ├─→ ① 사용자 모델 에이전트 (app/preference_commit/) — 칩(토픽)·충돌·근거 + 이론 매핑(가설 생성)
   │        [사용자 모델 쓰기 권한은 ①과 사용자 본인뿐]
   └─→ ② 플래너 (app/agents/planner.py) — 매개변수화된 액션 결정
   │        recommend(searchText, constraintsNote) / clarify(dimension, question) / answer / close
   │        구조 가드는 show_conflict 하나 (direct 충돌 = DB 사실)
   └─ recommend → [임베딩 검색: 도구] → ③ 추천 에이전트 (app/agents/recommender.py)
   │                 후보를 읽고 제약 위반 강등 → 3개 + 카드 ✓/~
   │                 읽는 것 = stated(명시 발화) + confirmed(사용자 확인) 기준만
   → 렌더러 (response_generator.generate_reply, §36 hedged — 결정 없음)
```

## 액션 어휘: MG-ShopDial 12-intent → 5 액션 (도출 근거)

Base: **MG-ShopDial** (Bernard & Balog, SIGIR 2023, arXiv:2304.12636) — e-commerce
멀티골 대화 코퍼스, ISO 24617-2 기반 12-intent 스키마. 루프 프레임은 **EAR**
(Lei et al., WSDM 2020) — Estimation(①)–Action(②)–Reflection(①의 피드백 경로).

3단계 도출:
1. **수행 주체 필터**: Disclose/Positive·Negative feedback은 사용자 행위 → 액션 아님
   (사용자측 라벨로는 사용 가능). Other는 잔여 범주. 에이전트 수행 가능 7개 남음.
2. **백엔드 효과로 병합**: 플래너 액션은 "시스템이 무엇을 하는가"로 구분, 표면 화법은
   렌더러 몫. Recommend→`recommend`(검색 발동). Elicit preferences+Clarification
   question→`clarify`(질문 생성, 검색 없음). Answer+Explain→`answer`(노출 상품·대화
   읽고 응답, 검색 없음 — MG-ShopDial에서 Answer가 전체 발화의 33.7%로 단일 최대
   intent인데 기존 우리 액션 공간에 없던 구멍). Greetings 종료→`close`(세션 스테이지
   전환). 시작인사·Interaction structuring은 렌더러가 자연 생성(템플릿 조립 시대의
   구분 이유가 LLM responder에선 소멸).
3. **도메인 고유 추가**: `show_conflict` — MG-ShopDial에 없는 우리 연구 고유 행동
   (감지된 선호 충돌의 외재화·사용자 해소). direct 충돌 객체 존재라는 DB 사실에만
   발동하므로 유일한 구조 가드로 유지.

병합으로 잃는 입도는 subtype(clarify: elicit|repair, answer: factual|justify)으로
LLM 출력에 보존 가능(연구 로그용, DB 영속화는 후속).

**PSCon 화행 가드 폐지**: 기존 accept→close, inquire→explain 가드는 화행 키워드
멤버십이라 혼합 화행에서 오작동(예: "이거 좋네요, 근데 무선인 것도 볼 수 있어요?" →
accept 매칭 → 조기 close). close/answer 판단은 문맥 판단이므로 LLM 4-vocab으로 이동.
화행 분류 자체는 annotation으로 유지(결정 경로에서 제외).

## 매개변수화된 액션 (플래너가 쿼리를 "하는" 게 아니라 인자를 내는 것)

EAR의 Action이 ask(어느 속성)까지 한 정책에서 내듯, 현행 clarify가 probe
dimension+question을 같은 호출에서 저작하듯 — recommend도 인자를 갖는다:

- `searchText`: 대화 전체의 사용자 발화(+피드백)를 반영한 **독립 한국어 검색문**
  (conversational query rewriting — QReCC NAACL'21 / ConvDR SIGIR'21 계열).
  긍정·주제 신호만 담는다.
- `constraintsNote`: 예산·필수·비선호의 자연어 요약 → rerank로 전달.

분업 근거: **NevIR (EACL 2024)** — bi-encoder 임베딩은 부정을 사실상 못 읽는다
(랜덤 이하). "커널형 싫어요"를 임베딩 쿼리에 넣으면 커널형이 더 잘 검색됨. 부정·제약은
후보를 실제로 읽는 cross-encoder격 LLM rerank에서만 처리 가능 → searchText(긍정)와
constraintsNote(제약)의 분리는 선택이 아니라 강제. 플래너에 상품 ID는 흐르지 않는다
(선별은 전부 ③).

## 추천이 읽는 것: stated + confirmed만 (evidence purity)

rerank 컨텍스트에서 미확인 추론(anchor_scores/motivation_scores 원점수) 제거. 대신:
- `statedConstraintsNote` (플래너 요약)
- `criteria` = IntentionTopic 중 explicitness=explicit **또는** status가
  confirmed/corrected_by_user (rejected_by_user/inactive 제외)
- `recentUtterances` (원문)

이유: (1) 미확인 추론이 추천에 들어가면 피드백 증거가 오염 — 추천은 "조건은 맞고
가치가 다른" 무색의 무대여야 선택의 잔여 변인이 숨은 가치가 됨. (2) correctable
조건이 진짜가 됨 — 칩 수정→confirmed→다음 추천에 실반영이라는 인과 경로가 구조적으로
보장. (3) 가치 측정은 현재 Functional-collapse 상태(synthesis-multi-v2 분석)라
피처로는 노이즈.

**이론 층(가치·동기)의 런타임 역할 = 가설 생성기** (F1 원칙의 세션 내 일반화):
점수→랭킹 직행은 차단, 토픽→이론→RIG 예측→플래너 컨텍스트(ragPrediction)→hedged
선제 질문→사용자 확인→confirmed 기준→추천의 경로만 허용. 가설 경로는 노이즈 내성
(틀린 가설은 싼 기각 + 기각도 증거), 피처 경로는 오류를 조용히 전파.

가설의 정의: 시스템이 생성했고, 사용자가 아직 검증하지 않았고, 검증 전까지 추천에
작용할 수 없는(격리) 명제. 칩·질문·충돌 카드는 가설의 검증 절차, §36 hedged 화법은
가설 상태의 언어적 표현.

## 의도 획득 3채널 (고전 CRS와의 차이 — 논문의 심장)

| 채널 | 작동 | 언제 |
|---|---|---|
| ② 추천=프로브 (관찰) | 연속·수동 | 모든 추천 턴 |
| ③ 외재화·수정 (칩/충돌) | 연속·수동 | 모든 추론 |
| ① clarify (질문) | 이벤트 구동 (플래너) | 정보 부족 또는 가설 확인 가치 |

직접 물으면 stated preference지 hidden intention이 아님(측정이 설문으로 퇴화).
elicitation을 질문에서 관찰+외재화로 옮긴 것이 EAR ask-vs-recommend에 대한 우리 답.
가설 작업 분해: 생성=①, 검증 일정=②(턴당 결정권자는 하나 — 6월 3-tier 사다리
시도-롤백이 근거; MACRS도 선택권은 Planner 단독), 결과 해석=①.

## 구현 노트

- 플래너+쿼리합성 통합으로 recommend 턴당 LLM 1 RT 절약 (라이브 스터디 지연 예산).
- 필드별 정규화·폴백: action ∉ 4-vocab → recommend, searchText 누락 → 현재 발화,
  dimension ∉ 12-vocab → None. 국소 실패 = 국소 강등 (기존 `_safe()` 패턴).
- mock 플래너: searchText = 사용자 발화 전부 join (턴1 도메인이 턴2 쿼리에 살아남아
  test_5 복구), close/answer는 기존 mock 화행 구문과 동일 구문으로 판정(시뮬 재현).
- CHI 장치 리스크: (1) 하중이 가치축→칩(토픽 추출)으로 이동 — 스터디 전 토픽 추출
  품질 검증이 최우선, (2) 턴 지연이 인지부하 DV를 오염 — 파일럿에서 지연 예산 필요,
  (3) 오프라인 부속(Concept 생애주기·WIMHF·spec)은 턴 루프 밖 유지.

## 검증된 인용 (2026-07-02 웹 검증 완료)

- EAR: Lei et al., WSDM 2020, arXiv:2002.09102
- MG-ShopDial: Bernard & Balog, SIGIR 2023, arXiv:2304.12636
- NevIR: Weller et al., EACL 2024, arXiv:2305.07614
- QReCC: Anantha et al., NAACL 2021, arXiv:2010.04898
- ConvDR: Yu et al., SIGIR 2021, arXiv:2105.04166
- MACRS: arXiv:2402.01135 / ChatCRS: arXiv:2405.01868 (포지셔닝용 — 채택 안 함:
  둘 다 카탈로그 검색을 KG/파라메트릭 지식으로 우회, 우리 문제엔 부적용)
- Jannach et al., ACM CSUR 2021 (10.1145/3453154) — CRS 액션 분류 백업 인용처
