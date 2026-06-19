# Railway 배포 런북 (Nixpacks · Docker 없음)

> 결정 근거는 `docs/plans/2026-06-16-formative-study-deploy-design.md` (§6, D4/D5/D8).
> **이 repo의 루트 = `valuecommit/`** (부모 디렉토리의 25GB CSV 덤프는 repo에 들어가지 않음).
> 한 GitHub repo로 **백엔드·프론트 2개 서비스**를 만든다. 빌드는 Nixpacks 자동.

## 0. 사전 (1회)

```bash
# valuecommit/ 에서
git push -u origin main          # GitHub: yestaehyung/chi_27_value_formative
```

Railway에서 **New Project → Deploy from GitHub repo → 해당 repo 선택.**

## 1. backend 서비스

| 설정 | 값 |
| --- | --- |
| **Root Directory** | `backend` |
| Build | Nixpacks 자동 (Python 감지) |
| Start | `backend/Procfile` 자동 → `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Volume** | mount path `/data` (SQLite + exports 영속) |

**Variables** (`backend/.env.example` 참고):

```
VC_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=<발급키>
VC_DEEPSEEK_MODEL=deepseek-chat
VC_SEED_DIR=seed_naver
VC_DB_PATH=/data/nv_study.db
VC_EXPORT_DIR=/data/exports
VC_CORS_ORIGINS=https://<frontend>.up.railway.app
```

> `VC_SEED_DIR=seed_naver` 빠지면 데모 시드(`seed/`)가 로드돼 NAVER 상품이 안 뜬다.
> `VC_DB_PATH`는 반드시 볼륨 경로(`/data/...`)여야 재배포 후에도 응답·설문이 보존된다.

## 2. frontend 서비스

| 설정 | 값 |
| --- | --- |
| **Root Directory** | `frontend` |
| Build | Nixpacks 자동 (Next.js → `next build`) |
| Start | 자동 `next start` (`$PORT` 자동 인식) |

**Variables:**

```
BACKEND_URL=https://<backend>.up.railway.app
```

> `next.config.mjs`의 `rewrites()`가 `/api/*`를 `BACKEND_URL`로 **서버 사이드 프록시**한다.
> 그래서 브라우저는 프론트 도메인만 호출 → CORS가 사실상 안 걸린다(그래도 백엔드 `VC_CORS_ORIGINS`는 안전장치로 설정).
> Railway 사설망을 쓰려면 `BACKEND_URL=http://<backend>.railway.internal:8080` 형태도 가능.

## 3. 배포 순서

1. backend 먼저 배포 → 공개 URL 확보
2. 그 URL을 frontend의 `BACKEND_URL`, backend의 `VC_CORS_ORIGINS`(프론트 URL)에 채움
3. 두 서비스 redeploy
4. 스모크: `https://<frontend>/study/survey` 접속 → 설문 → 튜토리얼 → 세션까지

## 4. 운영 주의

- **백업(필수):** SQLite는 연구 데이터. 주기적으로 볼륨의 `/data/nv_study.db`를 `sqlite3 .backup`으로 내려받거나 `/data/exports`(JSONL)를 보관.
- **리전:** Railway는 한국 리전 없음(미국/싱가포르). 진행자 동반 study라 지연 허용(D8).
- **LLM 교체:** `VC_LLM_PROVIDER` 한 줄(`deepseek`→`openai`/`anthropic`) + 해당 키.
- **로컬 시드 갱신 시:** `seed_naver/products.json`을 다시 커밋·push해야 배포에 반영됨(시드는 repo에 동봉, DB는 볼륨).
