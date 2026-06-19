# Formative Study 분리 + 실데이터 + 배포 설계

**작성일:** 2026-06-16
**성격:** 설계문서 (durable decisions + rationale). 구현 세부는 코드가 진실 — 이 문서는 *왜* 그렇게 했는지의 지도.
관련: `formative-study-design.md`(FS1), `pscon-analysis.md`, 코딩스펙 §14.2/§23/§36, 메모리 `naver-smartstore-data-decode`

> ⚠️ 이 문서는 **변하지 않는 결정 + 이유**만 담는다. 버튼/카피/컴포넌트 세부는 코드가 진실이므로 여기 적지 않는다.
> 구조적 결정(예: SQLite→Postgres)이 바뀔 때만 이 문서를 고친다. 잘게 쪼갠 작업은 별도 구현 plan으로.

---

## 1. 목적과 범위

기존 `valuecommit/` 모노 데모에서 **참가자용 formative study(`/study/*`)만 떼어내** 독립 배포하고,
더미 상품을 **실제 NAVER Smart Store 데이터**로 교체한다.

- **대상:** FS1 참가자 (N≈10, 진행자 동반, **원격 접속**)
- **상품 스코프:** **전자(기기 중심: 스마트워치·이어폰·노트북류) + 의류**
- **목표:** 추천 에이전트가 *진짜 NAVER 상품*에서 후보를 뽑게 하여 hidden-intention 관찰의 생태 타당성↑
- **비목표:** 추천 정확도, 대규모 트래픽, simulation/research 뷰 (참가자 앱에서 제외)

---

## 2. 확정된 결정 (Decisions + Rationale)

| # | 결정 | 이유 |
|---|---|---|
| D1 | **LLM = deepseek** (나중에 교체) | 이미 `.env` 설정·비용 최저. 교체는 `VC_LLM_PROVIDER` 한 줄. |
| D2 | **실데이터 사용** (더미 폐기) | "real 데이터" 취지 — 생태 타당성. |
| D3 | **스코프 = 전자(기기) + 의류** | trade-off가 또렷(가성비/브랜드/기능) → hidden intention 관찰 유리. |
| D4 | **배포 = 올-Railway, 2서비스, Docker-free** | 사용자가 Docker 비숙련 → Nixpacks 자동빌드로 운영 위임. 플랫폼 1개로 단순화. |
| D5 | **DB = SQLite + Railway 볼륨** (Postgres 아님) | N≈10엔 충분. 코드가 SQLite/WAL 전제로 작성됨. 볼륨+백업으로 영속·보호. |
| D6 | **가격 = 실데이터 역산** (합성/검색 아님) | 구매 테이블에 진짜 정가 존재(검증 99.5%). 합성은 think-aloud 오염 위험. |
| D7 | **가치모델: priceCue 유지 / 이미지·셀러필드 확보(enrich)** | `enrich_naver_images.py`(Naver 검색 API, ~78% 매칭)로 이미지·셀러등급·카테고리명·실거래가 보강 → 카드에 이미지+실거래가 표시. (구 '이미지 없음 / sellerCue 약화' 가정은 폐기; sellerCue 실제 가중 여부는 `algorithm-audit.md` 기준.) |
| D8 | **고정 IP 불필요** | 서비스는 도메인+HTTPS로 통신. 정적 CSV라 런타임 outbound 없음 → allowlist 대상 0. |

---

## 3. 데이터: 소스와 조인

상세 디코드는 메모리 `naver-smartstore-data-decode` 참조. 요약:

- 위치: `/Users/notaehyeong/Develop/naver_value_evaluation/*.csv.gz` (헤더 없는 TSV 4개, 각 Spark part-00000 한 조각)
- 컬럼 사전: `네이버스마트스토어20260514.xlsx`
- **추가 파일은 없음** (확정). 그래서 받은 4조각으로 끝낸다.

| 파일 | 테이블 | 제공 |
|---|---|---|
| `8f9dcd63…` (10G, 9col) | 상품/카탈로그 마스터 | 상품명·categoryId·status·등록일 |
| `1679696e…` (2G, 18col) | 리뷰 | 평점(col15=1~5)·리뷰수·포토비율 |
| `ef69a29b…` (2.7G, 7col) | 일별 지표 | 트래픽/인기 (col3=catalogId) |
| `a577f368…` (11G, 26col) | 구매 | **정가(col10)**·할인·결제·배송비·구매수 |

- **만능 조인키 = 19자리 `catalogId`** (각 파일 col3). 10자리 product_id 아님(샤딩 달라 거의 안 겹침).
  4M 샘플 검증: 제목+가격 22,419 매칭 / +평점 17,992 / 카테고리 22,419종.
- **결측 보강:** 브랜드·구조화 속성 → deepseek로 제목에서 파생. **이미지·셀러등급·카테고리명·실거래가 → `scripts/enrich_naver_images.py`(Naver 검색 API, ~78% 매칭)로 보강** → `seed_naver/products.json`에 `imageUrl`/`sellerName`/`sellerGrade` 등 존재. (구 '이미지·셀러 없음' 가정 폐기.)
- **한계(명시):** 가격은 *구매가 있었던 상품*만 존재 → 인기 편향. formative엔 수용 가능.

---

## 4. ETL 파이프라인 (오프라인, 1회성, DuckDB)

> 원칙: 25GB 압축 해제 금지. DuckDB가 `.csv.gz`를 스트리밍으로 읽는다.

```
read_csv(4× gz)                       # all_varchar, ignore_errors, delim='\t', header=false
  → 상품: status='판매중' 필터
  → 도메인 분류(기기 전자 + 의류)        # 1차: 제목 키워드 / 2차: 키워드 최빈 categoryId로 고정(노이즈↓)
  → catalogId로 join (상품 ⨝ 구매 ⨝ 리뷰 ⨝ 지표)
  → 집계: median(정가), avg(평점), count(리뷰), sum(트래픽), count(구매)
  → 기기 필터: 가격하한·기기키워드로 액세서리 제외
  → 도메인 균등 샘플 (전자 N / 의류 N)
  → deepseek 보강: 제목 → 브랜드 + 카테고리별 구조화 속성 + 정규화 상품명
  → 이미지/셀러/카테고리명/실거래가 보강: scripts/enrich_naver_images.py (Naver 검색 API, ~78%)
  → cue 파생: 기존 build_cue_summary (priceCue=카테고리내 상대가, §6.1)
  → emit seed_naver/products.json   # 기존 스키마 유지 (배포/실행 시 VC_SEED_DIR=seed_naver로 로드)
```

- 출력 형식은 **기존 `seed/products.json` 스키마 그대로** → 백엔드 로더(`products/seed_loader.py`) 무변경.
- `cueSummary`는 로더가 `build_cue_summary`로 파생하므로 JSON에 cue를 넣지 않아도 됨.
- 산출물은 시드로 고정 → **런타임에 외부 호출 0** (배포가 stateless web 1개로 축소).

---

## 5. 앱 변경 (참가자 study 추출)

실데이터에 가격·평점·리뷰가 있으므로 **변경 최소**.

**Frontend (`valuecommit/frontend`)**
- 유지: `app/study/*`, `components/{chat,preference,products}`
- 제거: `app/simulate`, `app/research`, `app/pscon` (+ 관련 컴포넌트). 랜딩은 study로 직행.
- 카드: 이미지 포함(enrich) + 평점+리뷰수+실거래가 중심 레이아웃 (이미지 누락분만 플레이스홀더)

**Backend (`valuecommit/backend`)**
- 유지 라우터: `sessions, turns, feedback, conflicts, preferences, study, meta, exports`
- 제거 라우터: `simulations, synthesis, pscon, research` — **제거 전 import 의존성 확인**(예: meta가 scenarios/concepts 제공하는지)
- 가치모델: `cue_extractor`(priceCue=실가격 유지, sellerCue 제거/근사), `scoring.py`(§14.2 가중치에서 seller 항 제거)
- **검색/카테고리 (2026-06-16 라이브 실행에서 발견된 버그):** `search.py`의 `detect_category`·`CATEGORY_KEYWORDS`가 구 데모 카테고리(스마트워치/노트북/무선이어폰…)를 가리켜 새 taxonomy(전자기기/의류)와 안 맞음 → 카테고리 필터가 무력화 → 전체 600개 혼합 풀에서 trade-off 슬롯에 **오프도메인 상품이 섞임**(예: '무선 이어폰' 검색에 래쉬가드 반바지). **수정(구현됨):** (1) `select_tradeoff_set`에 **상대 관련도 floor** `max(REL_FLOOR_MIN, top_rel×REL_FLOOR_RATIO)` — 대화체 질의("나 맥북 사고 싶어, 지금 고장났음")가 불용어로 점수가 통째로 낮아지는 데 강건; (2) `service_agent` 추천 검색 질의에 **시나리오 targetCategory 앵커**(`session.meta["category"]`)를 결합 — 해명성 답변 턴("혼자 고르고 싶어요")처럼 상품어 없는 발화에서도 상품 도메인 유지. detect_category 키워드맵 enumerate는 브리틀하여 채택 안 함(질의가 무엇일지 미리 알 수 없음). 임베딩(RAG) 하이브리드(OpenAI text-embedding-3-small)도 시도했으나 상품 텍스트가 **제목-only 노이즈**라 의도→상품 정렬이 안 됨("조깅할 때 음악"→에어팟 *키링*, cos 0.26~0.46 저대비) → **되돌림(2026-06-17)**. 재검토 전제: 상품 설명 enrichment 또는 LLM 카테고리 라벨링. (DeepSeek는 임베딩 API 없음 — chat 전용.) 또한 `select_next_action`이 `category`(=detect_category 결과)=None이면 **영영 clarify에 갇혀 추천 불가**한 버그 → `category`를 **시나리오 targetCategory로 폴백**(2026-06-17). 니트·원피스 등 구-데모 외 카테고리에서도 추천 단계 진입.
- §36 준수: 추론은 확정 사실로 표현 금지 (기존 정책 유지)

---

## 6. 배포 (Railway, Docker-free)

한 프로젝트 · 서비스 2개. Nixpacks 자동빌드(사용자가 Docker 안 만짐). 둘 다 git push 배포, HTTPS 자동.

```
[backend service]  root=valuecommit/backend
  build: Nixpacks(Python)   start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
  Volume /data
  env: VC_SEED_DIR=seed_naver            # NAVER 상품 시드 로딩 (생략 시 demo seed/ 로드돼 상품 불일치)
       VC_DB_PATH=/data/nv_study.db        # study DB (볼륨 위 영속)
       VC_EXPORT_DIR=/data/exports          # JSONL export = 연구산출물 → 볼륨에 영속
       VC_LLM_PROVIDER=deepseek  DEEPSEEK_API_KEY=***  VC_DEEPSEEK_MODEL=deepseek-v4-flash
       VC_CORS_ORIGINS=https://<frontend>.up.railway.app

[frontend service]  root=valuecommit/frontend
  build: Nixpacks(Node)     start: next start -p $PORT   (build: next build)
  env: BACKEND_URL=<backend 내부주소 또는 공개 URL>   # next.config.mjs rewrite가 /api/* 프록시
```

- 통신: 프론트→백엔드는 **도메인+HTTPS**(또는 Railway 내부 네트워크). **고정 IP 불필요**(D8).
- **백업(필수):** SQLite는 연구 데이터 → 주기적 `sqlite3 .backup` 또는 db/exports 다운로드를 운영 절차로. (재배포 시 볼륨은 보존되나 안전장치.)
- **사전 설문 영속:** FS1 사전 설문은 `Participant.survey`(JSON `{answers, profile}`)에 저장 → 연구자 `/research/surveys`에서 열람. DB 볼륨(D5)에 함께 보존되므로 별도 설정 불필요. (로컬 dev는 영속 `backend/nv_study.db` — 구 휘발성 `/tmp/nv_study.db`에서 2026-06-17 이전, `run_nv_study.sh`로 기동.)
- 설정은 전부 환경변수로 이미 오버라이드 가능(`config.py` 확인됨) → 코드 변경 없이 배포 구성.

---

## 7. 열린 항목 (나중 결정)

- **카테고리 라벨:** 데이터에 카테고리명 없음(숫자 ID뿐) → 제목 기반 추론 or 외부 NAVER 카테고리코드↔이름 매핑.
- **풀 크기:** 도메인별 N (초안: 각 100~150). FS1 진행하며 조정.
- **LLM 교체:** deepseek → openai/anthropic (FS1 일관성 검토 후). `VC_LLM_PROVIDER` 한 줄.
- **리전:** Railway는 한국 리전 없음(미국/싱가포르). 진행자 동반 study라 지연 허용 — 문제 시 재검토.
- **접근 제어:** 참가자 링크 방식(공유 링크 / 참가자 코드) — 경량으로.
- **시나리오(2026-06-16 발견):** 프리셋 9개는 구 데모(스마트워치/노트북/러닝화)로 NAVER taxonomy(전자/의류)와 불일치 — 특히 러닝화는 풀에 없음. FS1 설계상 시나리오는 *참가자별 custom*(회상인터뷰)이 정석이므로 **`custom` 경로가 실 study에 맞음**. 테스트/프리셋이 필요하면 전자·의류용 시나리오를 신규 작성. (조건은 `correctable` 고정 — FS1 단일조건.)

---

## 8. 다음 단계

이 설계가 OK면 → `superpowers:writing-plans`로 **잘게 쪼갠 구현 plan**(파일별 변경·순서·검증) 작성 → 배치 실행.
첫 배치 후보: (1) ETL 스크립트(DuckDB→products.json) + 미리보기 검증, (2) 라우터/라우트 추출, (3) Railway 배포 1서비스 스모크.
