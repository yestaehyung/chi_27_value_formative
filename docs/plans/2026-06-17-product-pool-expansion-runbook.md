# 상품 풀 확장/재샘플 런북 (sub-agent 라벨링 포함)

**작성일:** 2026-06-17
**용도:** 더 많은/다른 NAVER 상품을 추천 풀에 넣을 때의 **end-to-end 재현 절차**.
관련: `2026-06-17-product-labeling-retrieval-plan.md`(설계), 메모리 `naver-smartstore-data-decode`(원본 데이터)

흐름 한 줄: **materialize → build_stratified → [sub-agent label ×카테고리] → merge → clean → (image enrich) → load**

모든 명령은 `valuecommit/backend`에서 `.venv/bin/python ...` 로 실행.

---

## 0. 샘플 재료 준비 (`/tmp/nv` 없거나 더 많은 상품 필요 시)

원본 4개 `*.csv.gz`(프로젝트 루트)에서 바운드 샘플 추출(25GB 압축해제 금지, 스트리밍 head):
```bash
F1=part-00000-8f9dcd63-*.csv.gz   # 상품/카탈로그
F2=part-00000-1679696e-*.csv.gz   # 리뷰
F4=part-00000-a577f368-*.csv.gz   # 구매(가격)
mkdir -p /tmp/nv
gzip -dc $F1 | head -20000000 > /tmp/nv/s1.tsv   # 행 수↑ = 희소 카테고리 커버↑
gzip -dc $F2 | head -10000000 > /tmp/nv/s2.tsv
gzip -dc $F4 | head -20000000 > /tmp/nv/s4.tsv
```

## 1. 재샘플 — `scripts/build_naver_products_stratified.py`

카테고리별 구매수 상위 N개를 뽑아 `seed/products_stratified.json` 생성.
**더 많은 상품을 원하면 셋 중 하나:**
- `N_PER_CATEGORY` ↑ (카테고리당 개수; 기본 50)
- `TAXONOMY`에 **카테고리 추가** (이름·도메인·include/exclude 정규식). ⚠️ 새 카테고리는 **2-b**도 필요.
- `/tmp/nv` 샘플 행 수 ↑ (0단계)

```bash
.venv/bin/python scripts/build_naver_products_stratified.py
```

### 1-b. (새 카테고리 추가했다면) 태그 vocab 등록
`config/tag_taxonomy.json` 에 그 카테고리의 **허용 태그 목록**을 추가. 라벨러가 이 vocab에서만 태그를 고른다.

## 2. 라벨링 — **sub-agent, 카테고리당 1개** (병렬)

각 카테고리마다 `general-purpose` 서브에이전트 1개를 띄운다(총 ~13개; 한 번에 여러 개 디스패치, **API 529 뜨면 재시도** — 간헐적). 각 에이전트가:
1. `seed/products_stratified.json` 읽고 `category == "<CATEGORY>"` 필터(~50개)
2. `config/tag_taxonomy.json`의 `<CATEGORY>` vocab으로 각 상품을 `{id, tags, attributes, shortDesc}` 라벨
3. **환각 금지**(제목에 근거 있는 것만; 비-카테고리/액세서리/가짜는 `tags:[]` + shortDesc에 실제 정체 명시)
4. `seed/labels/<CATEGORY>.json` 에 JSON 배열로 저장

**프롬프트 템플릿** (`<CATEGORY>`만 치환):
```
Label real NAVER products for an HCI recommender (tags for retrieval + evidence).
READ products: <abs>/backend/seed/products_stratified.json — filter category == "<CATEGORY>".
READ allowed tags: <abs>/backend/config/tag_taxonomy.json — use the array under "<CATEGORY>".
For each: {id, tags(subset of allowed, only if title supports), attributes(small dict of TITLE-stated specs), shortDesc(ONE Korean sentence from title only), offCategory(true if this is NOT a genuine <CATEGORY> product — accessory/digital content/food/false keyword match; else false)}.
NO HALLUCINATION — tag only what the title states/strongly implies; empty tags fine. If offCategory is true, set tags [] and explain in shortDesc what the item really is. A genuine product with no taggable detail = offCategory false, tags [].
WRITE a JSON array to <abs>/backend/seed/labels/<CATEGORY>.json
Return a SHORT summary: count, avg tags/item, offCategory count, 3 examples, the flagged non-category items.
```
> 대안(서브에이전트 불가 시): `provider.generate_json(task=...)` 기반 deepseek 라벨링 스크립트로 자동화 가능. 단 품질은 Claude 서브에이전트가 더 좋았음(환각 적음, 엣지케이스 판단↑).

## 3. 병합 — `scripts/merge_labels.py`
```bash
.venv/bin/python scripts/merge_labels.py   # → seed/products_stratified.labeled.json
```
tags 병합 + **attributes는 메타(categoryId/domain)만 유지**(자유키 폐기), description=shortDesc.

## 4. 정크 정화 — `scripts/clean_pool.py`
```bash
.venv/bin/python scripts/clean_pool.py     # → seed/products_stratified.clean.json (제거 목록 출력)
```
태그 있는 상품은 유지, 태그 없는 것만 도메인별 정크 패턴(ELEC/CLO)으로 제거. **출력된 제거 목록을 검수** — 진짜 상품이 잘못 걸렸으면 해당 단어를 패턴에서 빼고 재실행; 새 정크 유형은 패턴에 추가.

## 5. 이미지·카테고리·실거래가 enrich — `scripts/enrich_naver_images.py` (Naver Search API)
새 풀의 catalogId들에 다시 돌려야 함(검색이 "이미지 있는 상품 우선"이라 이미지 없으면 노출 약함).
```bash
.venv/bin/python scripts/enrich_naver_images.py   # imageUrl/seller/category/실거래가 보강
```

## 6. 로드 + 인덱스(자동)
정화·enrich된 풀을 시드 `products.json`로 배치(예: `seed_naver/products.json`로 복사) 후 백엔드 재시작:
```bash
bash run_nv_study.sh   # lifespan이 load_seed_products(tags 포함) + FTS5 build_index 자동 수행
```
- DB가 기존 풀로 이미 시드돼 있으면 `load_seed_products`가 스킵하므로, 새 풀 반영하려면 `VC_DB_PATH` 새 파일 사용 또는 products 테이블 비우기.

## 7. 검증
- `VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/ -q` → **24 passed** 유지.
- "노트북/무선이어폰/원피스/운동용 이어폰" 질의 → 각 3개 + 모순 태그 없음 + (enrich 후) 이미지 有.
- 카탈로그 1,000개+에서도 질의 지연 한 자리 ms(BM25가 후보를 n=200으로 캡).

---

## 산출물 맵
`build_naver_products_stratified.py` → `products_stratified.json`
→ (sub-agent) `seed/labels/*.json`
→ `merge_labels.py` → `products_stratified.labeled.json`
→ `clean_pool.py` → `products_stratified.clean.json`
→ `enrich_naver_images.py` → (이미지 포함) → 시드 `products.json` → 백엔드 로드 + FTS5 인덱스.
