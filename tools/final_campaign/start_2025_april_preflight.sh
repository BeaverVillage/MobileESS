#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
DOT_GIT="$ROOT/.git"
VENV_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/mobileess-v28r2"
VENV="$VENV_ROOT/venv"
REQUIREMENTS="$ROOT/tools/final_campaign/requirements-v28.txt"
MARKER="$VENV/.requirements-v28.sha256"
cd "$ROOT"

# Git for Windows writes an absolute Windows gitdir into linked-worktree .git
# files. Translate it once for every child launched from WSL. Keeping this in
# the foreground start script also preserves normal Ctrl+C propagation.
if [[ -f "$DOT_GIT" ]]; then
  RAW_GIT_DIR="$(sed -n 's/^gitdir:[[:space:]]*//p' "$DOT_GIT")"
  if [[ -z "$RAW_GIT_DIR" ]]; then
    echo "[FAIL] linked-worktree gitdir marker missing: $DOT_GIT" >&2
    exit 2
  elif [[ "$RAW_GIT_DIR" =~ ^[A-Za-z]:[/\\] ]]; then
    GIT_DIR="$(wslpath -u "$RAW_GIT_DIR")"
  elif [[ "$RAW_GIT_DIR" = /* ]]; then
    GIT_DIR="$RAW_GIT_DIR"
  else
    GIT_DIR="$ROOT/$RAW_GIT_DIR"
  fi
  if [[ ! -d "$GIT_DIR" ]]; then
    echo "[FAIL] resolved gitdir not found: $GIT_DIR" >&2
    exit 2
  fi
  export GIT_DIR
  export GIT_WORK_TREE="$ROOT"
elif [[ ! -d "$DOT_GIT" ]]; then
  echo "[FAIL] Git metadata not found: $DOT_GIT" >&2
  exit 2
fi
git cat-file -e "HEAD^{commit}"

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

echo "[3/4] April source 30/30 검증"
"$VENV/bin/python" -m tools.final_campaign.prepare_v28r2_april_sources

echo "[4/4] 실행 환경·월말 모델 rollout 검증 후 April 30일 실행 시작"
if "$VENV/bin/python" -m tools.final_campaign.run_v28r2_april; then
  echo "[완료] 30일 실행 PASS. 최종 인증서를 검사합니다."
  exec "$VENV/bin/python" -m tools.final_campaign.audit_v28r2_april
else
  code=$?
  echo "[FAIL] 실행이 중단되었습니다. 다른 터미널에서 monitor_2025_april_preflight.sh를 확인하세요." >&2
  exit "$code"
fi
