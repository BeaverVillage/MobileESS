#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN='C:/Users/kjw39/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
REPO='C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/github_MobileESS_march_validity_fix'
export PYTHONPATH='C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/tmp/python_deps;C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/github_MobileESS_march_validity_fix'
cd "$REPO"

# NON_SCIENTIFIC_ENGINEERING_TEST
"$PYTHON_BIN" -m pytest -q tests/dayahead

# MIXED_EXISTING_REGRESSION_AND_NON_SCIENTIFIC_ENGINEERING
"$PYTHON_BIN" -m pytest -q tests/dayahead tests/test_pfr_ai_training.py tests/test_pfr_power.py tests/test_pfr_methods.py tests/test_git_identity.py

# FULL_REPOSITORY_REGRESSION (known Windows/Gurobi failures are reported, never hidden)
"$PYTHON_BIN" -m pytest -q tests

# STATIC_ENGINEERING_CHECKS
"$PYTHON_BIN" -m compileall -q dayahead
git diff --check

# SCIENTIFIC_FAIL_CLOSED_GATE (expected exit code 2 while AIDC authority is HOLD)
"$PYTHON_BIN" -m dayahead.cli aidc-status
