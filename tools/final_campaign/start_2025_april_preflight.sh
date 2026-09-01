#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
VENV_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/mobileess-v28r2"
VENV="$VENV_ROOT/venv"
REQUIREMENTS="$ROOT/tools/final_campaign/requirements-v28.txt"
MARKER="$VENV/.requirements-v28.sha256"
cd "$ROOT"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[1/4] WSL 실행 환경 생성"
  mkdir -p "$VENV_ROOT"
  if ! python3 -m venv "$VENV"; then
    echo "[FAIL] python3-venv가 필요합니다: sudo apt-get install python3-venv" >&2
    exit 2
  fi
fi

EXPECTED_SHA="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
CURRENT_SHA="$(test -f "$MARKER" && tr -d '\r\n' < "$MARKER" || true)"
if [[ "$CURRENT_SHA" != "$EXPECTED_SHA" ]]; then
  echo "[2/4] 필요한 Python 패키지 설치 (최초 1회)"
  "$VENV/bin/python" -m pip install --disable-pip-version-check -r "$REQUIREMENTS"
  printf '%s\n' "$EXPECTED_SHA" > "$MARKER"
else
  echo "[2/4] Python 패키지 확인 완료"
fi

echo "[3/4] 실행 환경과 April source 30/30 검증"
"$VENV/bin/python" -m tools.final_campaign.prepare_v28r2_april_sources
"$VENV/bin/python" -m tools.final_campaign.check_v28r2_runtime

echo "[4/4] April 30일 실행 시작"
if "$VENV/bin/python" -m tools.final_campaign.run_v28r2_april; then
  echo "[완료] 30일 실행 PASS. 최종 인증서를 검사합니다."
  exec "$VENV/bin/python" -m tools.final_campaign.audit_v28r2_april
else
  code=$?
  echo "[FAIL] 실행이 중단되었습니다. 다른 터미널에서 monitor_2025_april_preflight.sh를 확인하세요." >&2
  exit "$code"
fi
