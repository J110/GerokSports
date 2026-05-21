#!/usr/bin/env bash
# Preflight check — verify that every trace tag the validation gate
# expects to observe is present as a string literal in the source tree.
#
# Surfaces commit-design drift early: if a design memo predicts a
# FAIL→PASS flip on tag X but tag X has been deleted between
# memo-authoring and HEAD, the validation has no signal. Catch it
# before launching the replay.
#
# Usage:
#   scripts/preflight_validation_tags.sh
#   scripts/preflight_validation_tags.sh --tags TAG1,TAG2,TAG3
#
# Exits 0 if all expected tags found, 1 if any missing.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

DEFAULT_TAGS=(
  "trace_beta_sm_wicket_dispatch"
  "CROSS-FIELD-PAIRING-REJECT"
  "DIRECT-SCORE-COMMIT"
  "PARTNERSHIP-WRITE"
  "OVER-ARCHIVE-WRITE"
)

if [[ "${1:-}" == "--tags" && -n "${2:-}" ]]; then
  IFS=',' read -r -a TAGS <<< "$2"
else
  TAGS=("${DEFAULT_TAGS[@]}")
fi

SEARCH_PATHS=(
  "files/test_pipeline.py"
  "files/score_manager.py"
  "files/eyes"
  "files/scoreboard.py"
)

missing=0
for tag in "${TAGS[@]}"; do
  found=0
  for p in "${SEARCH_PATHS[@]}"; do
    if [[ -e "$p" ]] && grep -rqF "$tag" "$p" 2>/dev/null; then
      found=1
      break
    fi
  done
  if [[ $found -eq 0 ]]; then
    echo "MISSING: $tag — not found in source tree" >&2
    missing=$((missing + 1))
  else
    echo "ok: $tag"
  fi
done

if [[ $missing -gt 0 ]]; then
  echo >&2
  echo "$missing tag(s) missing. Validation gate has no signal for these." >&2
  echo "Fix: restore the emission site, or remove the tag from the" >&2
  echo "      validation gate's expected-tags list before launching." >&2
  exit 1
fi

echo "all $((${#TAGS[@]})) tag(s) present"
