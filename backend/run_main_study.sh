#!/usr/bin/env bash
# 본실험(main study) 백엔드 기동 — 라이브(Railway `v2_backend`)와 동일 구성.
#
# 라이브 대응표 (railway variables --service v2_backend):
#   VC_SEED_DIR   seed_amazon          ← 동일
#   VC_DB_PATH    /data/study_v2.db    ← 로컬은 backend/study_v2.db (같은 파일명)
#   VC_LLM_PROVIDER deepseek / VC_DEEPSEEK_MODEL deepseek-v4-flash  ← backend/.env 에서 로드
#   VC_APP_MODE   study                ← 라이브만. 로컬은 연구자 화면(/research)을 열어둔다.
#
# 풀 구성 (2026-08-06):
#   티셔츠 9,527 · 책상 2,926 · 블루투스 스피커 2,363 · 데스크체어 2,127 = 16,943
#   정본은 seed_amazon/products.json (git 추적). DB는 이 시드에서 파생되는 사본일 뿐이다.
#
# 처음 뜰 때 DB가 비어 있으면 시드 16,943개를 전량 적재한다 (LLM 호출 없음 —
# 프로필·벡터는 seed_amazon 에 이미 캐시돼 있다). 시드를 갈아끼운 뒤 기존 DB에
# 반영하려면 VC_SEED_UPSERT=1 로 한 번 띄운다 (신규 id만 추가, 기존 데이터 보존).
#
# 사용법:
#   bash run_main_study.sh                 # 포그라운드
#   nohup bash run_main_study.sh > .uvicorn_mainstudy.log 2>&1 & disown   # 백그라운드
#
# 포트 8000을 쓰는 이유: 프론트 next.config.mjs 의 /api/* rewrite 기본값이
# http://localhost:8000 이다. 다른 포트로 띄우면 화면이 이 백엔드를 안 본다.
set -euo pipefail
cd "$(dirname "$0")"

# 전량 풀(44,539·10카테고리, 2026-08-11)은 git 밖 seed_amazon_full 에 있다 —
# 벡터 202MB가 GitHub 한도를 넘어 볼륨(/data/seed_amazon)으로 배포한다.
# 로컬에 없으면(새 clone) scripts/build_full_pool_seed.py 로 재생성하거나 seed_amazon 폴백.
if [ -d "$PWD/seed_amazon_full" ]; then
  export VC_SEED_DIR="$PWD/seed_amazon_full"  # 본실험 활성 풀 (44,539개 · 10카테고리)
else
  export VC_SEED_DIR="$PWD/seed_amazon"       # 폴백 (16,943개 · 4카테고리)
fi
export VC_DB_PATH="$PWD/study_v2.db"        # 라이브 /data/study_v2.db 와 같은 이름
export VC_PORT="${VC_PORT:-8000}"

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$VC_PORT"
