#!/usr/bin/env bash
# Amazon(영어) 상품 풀 백엔드 기동 스크립트.
#
# NAVER 스터디(run_nv_study.sh, nv_study.db)와 분리된 별도 DB(amazon_study.db) + seed_amazon 시드.
# 두 DB는 서로 안 섞이며, NAVER로 되돌리려면 run_nv_study.sh로 다시 켜면 된다.
# LLM provider / API 키는 backend/.env 에서 자동 로드.
#
# 사용법:
#   bash run_amazon_study.sh                 # 포그라운드
#   nohup bash run_amazon_study.sh > .uvicorn_amazon.log 2>&1 & disown   # 백그라운드
set -euo pipefail
cd "$(dirname "$0")"

export VC_SEED_DIR="$PWD/seed_amazon"      # Amazon 상품/시나리오 시드 (영어, 600개)
export VC_DB_PATH="$PWD/amazon_ko.db"      # Amazon(한국어) 전용 DB — 영어 amazon_study.db와 분리

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
