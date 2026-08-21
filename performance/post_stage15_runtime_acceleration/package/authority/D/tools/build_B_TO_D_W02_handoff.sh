#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${1:-}"
if [[ -z "$ROOT" || ! -d "$ROOT" ]]; then
  echo "Usage: bash tools/build_B_TO_D_W02_handoff.sh /path/to/W02_delivery_root" >&2
  exit 64
fi
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="/home/jaewon/miniconda3/envs/power_v61/bin/python"
"$PY" "$HERE/tools/validate_B_W02_4POLICY_delivery_structure.py" --delivery-root "$ROOT"
TS="$(date +%Y%m%dT%H%M%S%z)"
OUT="$(dirname "$ROOT")/B_TO_D_W02_M1_M4_ACTUAL_${TS}.tar.gz"
(
 cd "$ROOT"
 find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
)
tar -czf "$OUT" -C "$(dirname "$ROOT")" "$(basename "$ROOT")"
sha256sum "$OUT" > "${OUT}.sha256"
echo "B_TO_D_W02_HANDOFF=$OUT"
