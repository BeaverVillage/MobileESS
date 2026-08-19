#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Compatibility implementation remains in the formerly released filename;
# this canonical entry point exposes the corrected 12-week campaign semantics.
exec bash "$HERE/RUN_FIRST6_REP_WEEKS_ACTUAL.sh" "$@"
