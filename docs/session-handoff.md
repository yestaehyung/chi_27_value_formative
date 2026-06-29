# 세션 핸드오프 (추천 에이전트 분석 + quick-fix·정리 번들)

**작성: 2026-06-27.** 이 세션 = 추천 에이전트 **7축 분석**(멀티에이전트 워크플로) + **quick-fix·정리 번들** 구현. 테스트 **55 green** (`cd backend && VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/ -q`).

## ✅ 이번 세션 완료 (A/B/C/E/D2 — 동작변경은 TDD/회귀가드 추가)
- **A. reply/rerank 정합** (`service_agent.py` recommend 분기): reply가 `pool[:3]`(rerank 전), 카드는 `select_tradeoff_set(reranked)`를 보여주던 불일치 → rerank+select **먼저**, 그 노출 셋으로 reply 생성. 가드 `tests/test_reply_grounding.py`. (대가: reply가 rerank와의 병렬 1개를 잃음 — D로 상쇄 예정.)
- **B. 충돌 확인메시지 도메인 누수 제거** (`conflict_resolver.py`): `MESSAGE_BY_ACTION`의 선물/최저가 문자열(유일하게 LLM 리라이트 미경유 — `api/conflicts.py`가 raw 반환) → `build_resolution_message`로 시나리오 중립 + 실제 토픽 라벨 근거. `tests/test_resolution_message.py`.
- **C. 죽은 코드 삭제** (grep 호출처 0 확인): `should_value_clarify`·`next_probe`/`covered_dims`·`MOTIVATION_SPEC.probe`·`BUCKET_PHRASE`·`LETTERS`/`LETTERS_CARD`·`generate_card_rationales`·`trust_score`/`popularity_score`·미사용 `MOTIVATION_DIMS` import. (피벗 잔재.)
- **E. retry 버그** (`provider.py`): `@with_retries`가 no-op `_augment_payload`(동기 훅)에 붙어 OpenAI/DeepSeek 실제 `_call`엔 재시도 없었음(+`coroutine never awaited` 경고) → `_call`로 이동. `tests/test_provider_retry.py`.
- **D2. latency — 화행분류 ∥ commit** (`service_agent.py`): `_classify_dialogue_acts`(DB 미접근)를 `run_preference_commit`과 `asyncio.gather` → 턴당 순차 LLM 왕복 1회 절약. dialogue_acts는 commit 후 채움(commit이 안 읽음 + `expire_on_commit=False`라 안전).
- **F. 문서 드리프트**: CLAUDE.md의 "3-tier clarify priority" 서술 → 피벗 후 실제(구조가드 → `action_decision`(LLM) → `build_value_question` 폴백; 동기 detect-only; RIG는 `ragPrediction` 한 필드)로 갱신.

## ⬜ 2주차 백로그 (분석에서 도출, 미구현 — 연구 정렬순)
- **D1. reply_suggestions off-path**: 입력칩을 응답 critical path에서 제거(별도 fetch/스트림). 새 엔드포인트+프론트 필요 → 스트리밍과 함께.
- **D3. 임베딩 async**: `embeddings._embed` 동기 `httpx.Client`가 이벤트 루프 블로킹(동시 턴 직렬화). `search_products` async화(핵심 API 파급) 또는 `to_thread`(SQLite 스레드안전 주의, `check_same_thread=False`).
- **답변 스트리밍(SSE)**: time-to-first-token ~10s→~2s. 단일 최대 체감 효과.
- **commit Stage2-6 background화**: 추천은 topic 제약만 필요 — anchors/concepts/relations/summary는 응답 후로. **참가자 칩 실시간성 유지하려면 hybrid**(칩 만드는 topic+conflict만 동기, 무거운 연구자 그래프는 background) + 2단계 응답. (사용자 질문 답: 순진하게 background면 칩이 한 턴 늦게 반영됨.)
- **hidden_intention_fit 라이브 제거**: `scoring.py`의 0.2 fit 점수항(데모 한국어 키워드 → 풀 편향)은 LLM rerank가 이미 하는 일 → mock에만 남기고 라이브선 제거. (반환 matched/weak 문자열은 이미 죽음.)
- **action_decision 프롬프트가 ragPrediction/values 사용**: 컨텍스트엔 들어가나 프롬프트가 "recentTurns만 읽어라" → RIG 선제예측이 실질 무효. hedged 선제질문으로 활성화.
- **fail-loud-on-empty** (기존 항목 B): 필터 0건 시 전체 카탈로그 silent 폴백 대신 hedged 되묻기.
- **키워드 폴백 정리**: `EXPECTED_ANCHORS_BY_GOAL`/`build_value_question`의 "선물"→Social 등 → 시나리오 seed 메타 or LLM.
- **algorithm-audit.md 갱신**: `scoring.compute_product_score`가 0.6/0.2/0.2인데 문서는 §14.2 0.30/0.20/…(2026-06-23 trust/popularity 제거 후 불일치).
- **피드백→동기 감지**: `fetch_motivation_signals`가 발화만 봄 — 선택/거부 피드백 미반영(프로젝트 핵심 명제 강화 여지).

## LangGraph: 도입 불필요 (2026-06-24 결정 재확인)
제어흐름 거의 선형(순차 LLM 4~6단계), 퍼지 분기 1곳(`action_decision`), 루프·재시도 0. 복잡성은 **상자 안**(commit/scoring 휴리스틱)이지 오케스트레이션이 아님. 대신 swappable retrieve·응답후 background 큐·프롬프트 캐싱이 실효.

---

# 세션 핸드오프 (추천 로직 하드코딩 제거 + 예산 구조화 + 풀 확장 준비)

**작성: 2026-06-24.** 이 세션 = **추천 결과 버그 수정**(모니터·코트) + **하드코딩 제거** + **원본 덤프 풀 확장(F) 준비**. (이전 2026-06-10 UI/PSCon 핸드오프는 맨 아래 보존)

## ✅ 이번 세션 완료 — 테스트 35 green (`cd valuecommit/backend && .venv/bin/python -m pytest tests/ -q`)

**1. 카테고리 하드코딩 제거 → 모니터 버그 (라이브 DeepSeek 검증됨: 모니터 3개 나옴)**
- 원인: `CATEGORY_KEYWORDS`(7개 하드코딩)+`detect_category` substring이 "노트북이랑"의 노트북 오인 + 카테고리 하드필터가 임베딩이 올린 모니터를 덮어씀.
- 수정: `search.py`에서 `CATEGORY_KEYWORDS`/`detect_category` **삭제**, 카테고리 하드필터 제거(임베딩+BM25+빈결과 폴백 3곳). `service_agent.py::_update_surface_intent` 키워드 카테고리 안 씀 → category=시나리오 기본값(`session.meta.category`).

**2. 예산 구조화 (B) → 코트 가격 역전 (라이브 검증됨: 10-20만 → 108/119/149k)**
- 원인: `parse_budget_won` 첫 숫자만 → "10-20만"이 "예산 10만 이하"로 역전.
- 수정(LLM이 숫자 추출→코드는 산수, 파서 제거): `scoring.py`(`parse_price_range`=mock/폴백, `price_in_range`=산수필터), `models.py`+`database.py _migrate`(snapshot `price_min/price_max` 컬럼), `prompts.py`(topic_extraction 스키마에 priceMin/priceMax + 규칙1줄, 가격 예시 삭제), `mock_rules.py`(`_topic` price_min/max 방출), `merge.py`(hints carry), `state_builder.py`(snapshot set), `service_agent.py`(search에 전달), `topic_extractor.py`(키워드 예산 가드 **삭제**).

**3. "recommend인데 카드 0개" → 빈 풀 폴백**
- 원인: `search_products`의 `if ids:`에서 retrieve id가 DB에 없으면(재시드/스테일 캐시) candidates=[]→빈 풀.
- 수정: `search.py` id매핑 후 `if not candidates: candidates = db.query(all)`.

**새 테스트**: `tests/test_category_hard_filter.py`, `tests/test_price_range.py`.

**아키텍처 결정**: LangGraph 도입 **안 함**(버그는 상자 안 휴리스틱이지 오케스트레이션 아님; 감사상 구조 단단·하드코딩은 products/ 레거시 섬에 집중). 원칙: LLM이 open→closed 깔때기, 코드는 closed만(산수 OK), 라이브 경로 하드코딩 NL 금지, mock 결정론 룰은 OK.

## ⬜ 다음 — F. 원본 덤프 풀 확장 (사용자 최우선, 진행 중에 멈춤)
**왜**: 코트 남은 문제(자켓-아닌-코트·성별)는 데이터 문제(라이브 확인). 현재 풀 여성 코트 ~0. **실현가능 확인**: 원본에서 여성 아우터 10-20만 **150개(가치큐 115개)** 샘플됨.

**원본 덤프** (`/Users/notaehyeong/Develop/naver_value_evaluation/*.csv.gz`, 탭·헤더없음, duckdb로 스트림):
- product `part-…8f9dcd63…`(10GB): col2=catalogId,col3=categoryId,col4=title,col8=status
- purchase `part-…a577f368…`(11GB): col02=catalogId,col09=정가,col11=할인,col20=배송비
- review `part-…1679696e…`(2GB): col02=catalogId,col07=type(일반/한달사용),col14=score,col16=정상
- daily `part-…ef69a29b…`(2.7GB): col2=catalogId,col3-6 지표

**파생 파켓 (⚠️ `/tmp` — 재부팅 시 사라짐, duckdb로 재생성 필요)**: `nv_prod`(cat,title,categoryId,ever_active 973K)·`nv_price`(cat,price,sales,discount_rate 547K)·`nv_rev`(cat,reviews,rating,longterm_reviews 419K). 조인키=`cat`. duckdb 1.5.3(venv), `.df()` 금지(numpy없음)→`.show()`.

**핵심 발견**: 제목 정규식은 샘(테니스화 "court", 골프웨어) → **categoryId(구조화)로 분류**해야 클린(테니스화 ID≠코트 ID 확인). 단 categoryId는 숫자뿐·이름없음 → ID→이름 매핑(네이버 트리/Search API; enrich가 categoryPath로 이미 사용) **또는** LLM 라벨. 추천: 하이브리드(categoryId로 묶고 각 카테고리 1회 LLM 라벨=type/gender → 저렴·재사용).

**F 다음 스텝**: ① categoryId별 그룹핑으로 "여성 아우터 categoryId" 식별+상품수 집계(←여기서 멈춤) ② 그 ID들에서 클린 샘플 ③ LLM 라벨(gender·garmentType, 기존 seed/labels 인프라) ④ 재시드+재임베딩(`seed_naver/product_vectors.json`)+검증.

## ⬜ 작은 것들
- **B. fail-loud-on-empty**: 제약 적용 후 0건이면 조용히 버리지 말고(현 `if passing: candidates=passing`) → 되묻기("그 조건엔 없어요, 올릴까요?"). `search.py`+`service_agent.py`.
- **E. gift-text 누수**: `preference_commit/conflict_resolver.py` `MESSAGE_BY_ACTION`의 "최저가보다 선물로…" 하드코딩 → 시나리오 중립.
- off-domain·성별 = F 라벨링으로 해결. 사소: 모니터 답변이 "노트북도 보여드렸"이라는데 실제 상품엔 없음(reply가 최종목록과 어긋남).

## ⚠️ 재시작 시 주의
- **실행 서버 재시작 필수** = 이 세션 코드 반영 + **스테일 인메모리 벡터 리셋**(no-cards의 트리거였음). NAVER 백엔드: `bash run_nv_study.sh`(detached).
- `/tmp` 파켓·임시 DB는 재부팅 후 소실 → F 하려면 파켓 재생성.

---

# 세션 핸드오프 (UI 개선 + PSCon 04 기능)

**작성:** 2026-06-10. 컨텍스트 압축 후 작업 이어가기용. 이 세션은 주로 **프론트 UI 개선**과 **신규 04 기능(PSCon 실대화 시각화 + 배치 분석)**을 했다.

## 현재 실행 상태 (중요)
- **백엔드**: uvicorn `:8000`, provider=**deepseek**(`backend/.env`). **detached(setsid, PPID=1)** → 터미널 닫혀도 살아있음. 코드 바꾸면 **수동 재시작 필요**(`--reload` 아님).
- **프론트**: `next dev` `:3000`. (detached 아님 — 터미널 닫으면 꺼짐; 아래 명령으로 재기동)
- **🔄 진행 중: PSCon 전체 배치 분석**(648건)이 **병렬(동시6)** detached로 돌고 있음 → `backend/data/pscon_analysis.json`에 점증 저장. 모니터: `tail -f /tmp/pscon_batch.log`. 끝나면 `/pscon` 목록에 "분석됨"이 648까지 차고 각 대화 뷰어 **우측(좌 대화/우 방사형)**에 그래프가 뜸. 관찰: 실대화가 Functional 위주(~0.7–0.84)·latent 거의 0 → "PSCon explicit-heavy" 가설이 데이터로 드러남.
- 진행률 한 줄: `curl -s localhost:8000/api/pscon/conversations | python3 -c "import sys,json;print(json.load(sys.stdin)['analyzedCount'],'/648')"` · 배치 살아있나: `ps -o ppid=,etime= -p $(pgrep -f scripts/analyze_pscon)`

## 운영 명령어 (모두 detached)
```bash
# 백엔드
setsid nohup bash -c 'cd valuecommit/backend && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000' > /tmp/vc_backend.log 2>&1 < /dev/null &
# 프론트
setsid nohup bash -c 'cd valuecommit/frontend && exec npm run dev' > /tmp/vc_frontend.log 2>&1 < /dev/null &
# PSCon 배치 (backend에서; 숫자=대화수, 생략=전체 648; 재실행=이어서)
setsid nohup bash -c 'cd valuecommit/backend && exec .venv/bin/python scripts/analyze_pscon.py' > /tmp/pscon_batch.log 2>&1 < /dev/null &
# 배치 중단: kill <pid>  (pkill -f 는 자기매칭 위험 → pid로)
# 포트 점유 pid: ss -tlnp | grep ':8000 '
```

## 이번 세션에 한 것 (done)

### 랜딩 / 디자인 시스템
- 랜딩 `/` = **런처**(번호 01·02·03·04 + 역할칩). 헤더 로고 = `ValueCommit` 워드마크(V박스 제거). `app/page.tsx`, `app/layout.tsx`.
- **폰트**: Google Sans(Display=`h1–h3`, Text=본문) + Noto Sans KR. `--kr-fallback` CSS 변수. `app/layout.tsx`(Google Fonts link) + `globals.css`.
- **에이전트 아바타**: DiceBear `dylan`(seed=**Mia**) — `components/chat/AgentAvatar.tsx`. 채팅·이해패널·첫인사·생각중의 "V" 대체. (사람 페르소나=notionists 와 구분)

### 시뮬레이션 (`/simulate`) = "합성 데이터 생성 시뮬레이션"
- 페르소나 풀 = **Nemotron-Personas-Korea** 50명(비례추출 seed 42) → `seed/personas_nemotron.json`. 샘플러 `scripts/sample_nemotron_personas.py`. `load_personas()`가 이 파일 우선.
- 페르소나 선택 = **반응형 카드 그리드 + notionists 아바타 + 좌-정체성/우-10내러티브 모달**.
- ⚠️ Nemotron엔 쇼핑 trait 없음 → 현재 결정적 `UserAgentRunner`로 돌리면 중립 degenerate. (trait는 대화 합성으로 만드는 게 미래 작업)

### 참가자 세션 (`/study/session/[id]`)
- 우측 패널 380→**440px**, 세로 오프셋 7.5→**7rem**, AnchorRadar 180→**260px**.
- **ProductCard 재설계**(`components/products/ProductCard.tsx`): 정보박스 3개 **높이 정렬**(flex), 피드백 버튼 **박스 바깥 좌측하단**, 불릿→✓/~ 체크행, 셀러명 보조라인.
- **피드백 버튼**(`ProductFeedbackButtons.tsx`): **비교 버튼 제거**(남: 좋아요·싫어요·자세히·선택). **싫어요 이유 = 모달(portal)**.
- **CurrentUnderstandingPanel**: 칩 수정 = **기준 카드**(맞아요/아니에요 항상 노출 + 중요도·수정·근거 항상 노출, "더보기" 없앰). absolute 드롭다운 제거 → 스크롤 잘림 해결.

### 연구 대시보드
- **OntologyGraph**(`components/research/OntologyGraph.tsx`): 라벨 흰색 halo(겹침 가독성) + 노드 간격↑, **범례 항상 표시**(노드 선택해도 안 사라짐).

### 04 기능: PSCon 실대화 시각화 + 배치 분석 (신규)
- 백엔드 `app/api/pscon.py`: `../../PSCon/dataset/conversation_en_fully_rated.json`(648건) lazy 로드. 라우트: `GET /api/pscon/conversations`(목록+`analyzed`플래그), `GET /api/pscon/conversations/{id}`(대화+ratingMap+미리계산 `analysis`).
- 프론트: `app/pscon/page.tsx`(목록·검색·"분석됨" 배지), `app/pscon/[convId]/page.tsx`(스터디 채팅 스타일 뷰어). 칩은 **원어 그대로**(Reveal/Clarify…) + 상단 범례. user=intent·keywords, system=action·"제시한 선택지"(clarifying_attribute)·"추천 상품"(👍좋아요/👎싫어요=user_rating).
- **배치 분석**: `scripts/analyze_pscon.py` → 각 대화의 user 발화를 **우리 `run_preference_commit` 파이프라인**에 흘려 anchor_scores+topics 추출 → `backend/data/pscon_analysis.json`에 저장(재개·점증). 핵심 함수 `analyze_one_conversation`(pscon.py). 웹은 이 결과를 **즉시** 시각화(뷰어에 AnchorRadar). on-demand 분석 버튼/라우트는 **제거함**(느려서 일괄로 전환).
- 검증됨: 짧은 대화 #60759 → Functional 0.34·Social 0.19, topic "여자친구에게 줄 선물".

## 남은 일 / 열린 이슈 (todo)
1. **PSCon 전체 배치 완료 확인** (현재 진행 중, 648건). 끝나면 `analyzedCount=648`. 일부 실패 대화 있으면 재실행으로 보충.
2. **레이더 축은 7 유지**(사용자 결정). 단 topic은 trait 5에만 매핑 → Hedonic/Utilitarian 축은 ~0. (의도된 현 상태)
3. **loose end — 옛 6-anchor 잔존**: `seed/scenarios.json`의 `groundTruthHiddenIntentions`, `seed/personas.json` valueOrientation 이 `affective/hedonic` 옛 이름. 2층 모델과 불일치(평가·시뮬 정합용 정리 필요).
4. **참가자 trait 누적 미완**: `Participant`에 trait 점수 1급 컬럼 없음(spec_markdown·Concept로만 암묵 존재).
5. ✅ **연구 대시보드 분리(완료)**: `/research/sessions`에 모드 탭(참가자 manual / 시뮬 / PSCon). 기본 목록은 `mode!=pscon`로 PSCon 제외(+ N+1 회피), `?mode=` 필터, `modeCounts` 배지, pscon 탭 최근 100 cap. **Latent Yield 지표도 pscon 제외**(`compute_latent_yield`가 session join으로 `mode!=pscon`). 남은 미세 오염: pscon 분석이 cross-session **Concept TBox**엔 여전히 기여 → 원하면 pscon 분석을 topics+anchors만 하는 lite 파이프라인으로(동시에 속도도 ↑).
6. **후속 제안(보류)**: 중요도 "필수/중요/선호" 세그먼트 직접선택(백엔드 액션 추가 필요), 레이더 자체를 수정 surface로(가치수준 correction), PSCon liked/disliked를 분석에 피드백으로 반영(v2), 시뮬 User Agent를 LLM 내러티브 구동으로.

## 검증 루틴
- 프론트 타입: `cd frontend && ./node_modules/.bin/tsc --noEmit` (dev 중엔 `next build` 금지).
- 백엔드 테스트: `cd backend && VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/ -q`.
- 변경 후 백엔드는 detached로 **수동 재시작**해야 반영됨.

## 사용자 작업 선호 (메모리에도 저장됨)
대화형 옵션 제시 + 추천 후 "이대로 갈까요?"를 선호. 구조화 다지선다(AskUserQuestion)는 비선호. HCI 연구자라 **근거/이유**를 중시("왜 그렇게 했어?"). 빠르게 반복하며 작은 것 즉석 수정.
