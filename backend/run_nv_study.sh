#!/usr/bin/env bash
# NAVER formative-study 백엔드 기동 스크립트.
#
# 이 설정으로 켜야 (1) naver 상품 시드, (2) 올바른 study DB가 로드된다.
# LLM provider / API 키는 backend/.env 에서 자동 로드된다 (커맨드에 넣지 않음).
#
# 사용법:
#   bash run_nv_study.sh                 # 포그라운드 실행 (로그가 화면에)
#   nohup bash run_nv_study.sh > .uvicorn_naver.log 2>&1 & disown   # 백그라운드(세션 종료해도 유지)
set -euo pipefail
cd "$(dirname "$0")"

export VC_SEED_DIR="$PWD/seed_naver"   # naver 상품/시나리오 시드
export VC_DB_PATH="$PWD/nv_study.db"   # 영속 DB (/tmp 아님 — 재부팅에도 보존됨)

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
