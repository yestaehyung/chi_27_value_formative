#!/usr/bin/env bash
# 본실험(main study) 백엔드 기동 — 3과제 카테고리 전용 풀.
#
# 왜 amazon_ko.db가 아니라 새 DB인가:
#   amazon_ko.db에는 파일럿 데이터가 들어 있다 (참가자 33 / manual 세션 48 / 턴 193 /
#   상품 노출 314). 그 세션들이 참조하는 상품은 이번에 아카이브한 28개 카테고리라, DB에서
#   상품을 지우면 product_impressions가 고아가 되어 파일럿 데이터의 의미가 깨진다.
#   본실험은 새 데이터 수집이므로 DB를 분리하는 편이 분석에도 낫다.
#
# 풀 구성 (2026-07-28, scripts/augment_amazon_main_study.py):
#   블루투스 스피커 2,318 · 티셔츠 2,318 · 책상 1,159 + 데스크체어 1,159 = 6,954
#   세 과제 깊이가 같아야 과제 간 차이를 '카테고리 특성'으로 읽을 수 있다.
#   비과제 28개 카테고리는 seed_amazon/archive_28cat_*.json 으로 분리 보관
#   (scripts/archive_nonstudy_categories.py --restore 로 복구 가능).
#
# 사용법:
#   bash run_main_study.sh                 # 포그라운드
#   nohup bash run_main_study.sh > .uvicorn_mainstudy.log 2>&1 & disown   # 백그라운드
#
# 주의: 기존 :8000(amazon_ko.db 파일럿 서버)과 포트가 겹치지 않게 8001을 쓴다.
#       LLM provider / API 키는 backend/.env 에서 자동 로드.
set -euo pipefail
cd "$(dirname "$0")"

export VC_SEED_DIR="$PWD/seed_amazon"       # 아카이브 후의 활성 풀 (6,954개)
export VC_DB_PATH="$PWD/main_study.db"      # 본실험 전용 — 파일럿 amazon_ko.db와 분리
export VC_PORT="${VC_PORT:-8001}"

exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$VC_PORT"
