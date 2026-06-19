# ValueCommit Shopping Agent Demo

쇼핑 대화에서 사용자의 발화·상품 반응·chosen-rejected 피드백을 근거로 **value-grounded hidden
intention ontology**를 구축하고, 새 피드백이 기존 선호 추론과 충돌할 때 사용자가 이를
검토·수정(**Preference Commit**)할 수 있게 하는 연구용 데모입니다.

> 이 데모는 쇼핑 추천을 잘하는 시스템이 아니라, hidden intention state가 어떻게
> 생성·수정·충돌·검증되는지 **관찰 가능한 데이터와 UI**를 만드는 것이 목적입니다.

## 실행 방법

### 로컬 (권장)

```bash
# 1. Backend (FastAPI, :8000)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# 2. Frontend (Next.js, :3000) — 별도 터미널
cd frontend
npm install
npm run dev
```

→ http://localhost:3000 접속

### Docker Compose

```bash
docker compose up --build
```

### LLM Provider

`backend/.env` 파일로 설정합니다 (git에는 커밋되지 않음):

```bash
# OpenAI (현재 설정)
VC_LLM_PROVIDER=openai
VC_OPENAI_MODEL=gpt-4o-mini          # gpt-5 계열 사용 시 VC_OPENAI_REASONING_EFFORT 적용
OPENAI_API_KEY=sk-proj-...

# 또는 Anthropic
# VC_LLM_PROVIDER=anthropic
# ANTHROPIC_API_KEY=sk-ant-...

# 또는 API 키 없이 (결정적 규칙 엔진 — 데모 시나리오 그대로 재현)
# VC_LLM_PROVIDER=mock
```

실제 LLM 사용 시 매 turn마다 intent 분류 → topic 추출 → anchor/concept 매핑 →
relation → conflict 감지 → 응답 생성까지 5~7회 호출이 발생합니다 (gpt-4o-mini
기준 turn당 약 10~25초). 테스트(`pytest`)는 항상 mock으로 실행됩니다.

## 데모 시나리오 (선물용 스마트워치, 스펙 §24)

1. `/study/session/new` 에서 **선물용 스마트워치** 시나리오로 세션 시작
2. 입력: `운동 좋아하는 친구에게 줄 스마트워치를 찾고 있어요. 브랜드는 잘 몰라요.`
   → trade-off 상품 A/B/C 추천 + understanding chip 생성
3. 입력: `가능하면 저렴한 게 좋아요.` → "가격이 낮을수록 좋음" topic 생성
4. 상품 A(초저가)에 👎 싫어요 + 이유 `선물인데 너무 저렴해 보이면 좀 그래요.`
   → **direct conflict** (priority_shift) → Conflict Card 표시
5. `가격 상한은 유지하되 너무 저렴한 상품은 제외하기` 선택
   → avoidances에 "초저가로 보이는 상품 제외" 추가
6. 상품 B에 👍 좋아요 → **chosen-rejected pair** 자동 생성
7. `/research/pairs` 에서 **⛏ Pair Mining 실행** → "흔하지 않은 선물의 특별함" 같은
   discovered feature 후보 생성 → `/research/features` 에서 승인 시 concept으로 편입

## 화면

| URL | 설명 |
|---|---|
| `/study/session/new` | Manual participant mode (study condition 선택: baseline / explanation_only / correctable) |
| `/study/session/:id` | 채팅(좌) + 상품/선호 패널(우): understanding chips, conflict card, evidence drawer, anchor radar |
| `/simulate` | persona × scenario user-agent 시뮬레이션 + evaluation (topicRecall, anchorScoreMAE 등) |
| `/research/sessions` | 세션 목록 + JSONL export |
| `/research/session/:id` | replay · ontology graph · snapshot timeline · conflicts · pairs · evidence table |
| `/research/pairs` | chosen-rejected pair + product diff + inferred hidden reason, pair mining 실행 |
| `/research/features` | WIMHF-style discovered features 검토/승인 |

## 아키텍처

```
frontend (Next.js 14 + TS + Tailwind)
  └─ /api/* 프록시 → backend (FastAPI + SQLAlchemy + SQLite)
       ├─ agents/        service_agent(턴 처리·action 선택), user_agent(시뮬레이션)
       ├─ ontology/      topic_extractor → anchor_mapper → conceptualizer → relation_classifier → state_builder
       ├─ preference_commit/  commit_engine, conflict_detector(recall-first), conflict_resolver
       ├─ products/      keyword search + scoring(§14.2) + trade-off sampler
       ├─ wimhf/         pair_builder, diff_builder, feature_miner, ontology_expander
       ├─ llm/           provider-agnostic wrapper (MockLLMProvider 기본, Anthropic 선택)
       └─ evaluation/    simulation_eval, JSONL export(§21)
```

3-layer ontology: **Behavior/Evidence** (turn·impression·feedback·cue) → **Facts/Intention**
(topic·concept·relation·conflict) → **Theory/Value** (Functional · Conditional · Epistemic ·
Social · Affective · Hedonic).

## 테스트

스펙 §35의 Demo Acceptance Test 6종 + 부가 테스트:

```bash
cd backend
.venv/bin/python -m pytest tests/ -v
```

## 데이터 Export

`/research/sessions` 의 **JSONL Export** 버튼 또는 `POST /api/exports/run` →
`backend/exports/` 에 sessions / turns / product_impressions / feedback_events /
ontology_topics / ontology_relations / preference_state_snapshots / conflicts /
conflict_resolutions / chosen_rejected_pairs / discovered_features `.jsonl` 생성.

## 주의 (스펙 §36)

에이전트가 추론한 내용은 절대 확정 사실처럼 표현하지 않습니다. 내부적으로는 Social/Affective
score를 다루더라도 사용자 UI에서는 "~것 같아요", "맞는지 확인해 주세요" 같은 **맥락 제한적이고
수정 가능한 표현**으로만 번역됩니다.
