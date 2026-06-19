#!/usr/bin/env bash
# 전원 3세션 맞추기 — 멀티 세션(매칭+대비, Participant 묶음)을 아직 안 한 persona 전부 실행.
# 이미 멀티가 끝난 persona(산출 md 존재)는 자동 스킵 → 결과적으로 200명 전원이
# 단일 1 + 멀티 2 = 3세션이 된다.
#
# 실행:
#   setsid nohup bash ~/yeo/naver_value_evaluation/valuecommit/backend/scripts/run_multi_all.sh \
#     > /tmp/multi_all.log 2>&1 < /dev/null &
# 모니터:
#   tail -f /tmp/multi_all.log
#   grep -c "✓" /tmp/multi_all.log     # 완료 persona 수
#
# 중간에 죽어도 같은 명령으로 다시 띄우면 이어서 돈다.
set -euo pipefail
cd "$(dirname "$0")/.."   # → backend/

echo "[멀티 전원] 시작 — 대상 200명 중 미완료분 (동시 4)  $(date '+%H:%M:%S')"
VC_SYNTH_CONCURRENCY=4 .venv/bin/python scripts/run_multi_session_simulations_v2.py 200

echo ""
echo "✅ 완료  $(date '+%H:%M:%S') — 검수: data/synthesis_multi_v2/ · /simulate 합성 검수 (🔗 배지)"
