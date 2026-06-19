#!/usr/bin/env bash
# NAVER study 백엔드 — 개발용(--reload). 코드(.py) 수정 시 자동 재시작된다.
#
# ⚠️ 실제 스터디 실행에는 run_nv_study.sh 를 써라(--reload 없음).
#    --reload는 코드 변경마다 서버를 재시작하므로, 참가자 세션 도중 끊길 수 있다.
#
# 사용법:
#   bash run_nv_study_dev.sh
#   nohup bash run_nv_study_dev.sh > .uvicorn_naver.log 2>&1 & disown   # 백그라운드
set -euo pipefail
cd "$(dirname "$0")"

export VC_SEED_DIR="$PWD/seed_naver"   # naver 상품/시나리오 시드
export VC_DB_PATH="$PWD/nv_study.db"   # 영속 DB

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
