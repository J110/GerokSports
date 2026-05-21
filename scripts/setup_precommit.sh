#!/bin/sh
# scripts/setup_precommit.sh — install the project pre-commit hook with venv preference.
#
# Idempotent: re-running overwrites the hook with the current canonical content.
# Fails loudly if files/.venv/bin/python is missing (does NOT silently
# fall back to system python3 — that would surface the Python 3.9 vs
# 3.10+ syntax mismatch later as a confusing "Layer 1.5 FAILED" with
# a TypeError on eyes/agent.py's `int | None` annotation. Fail at
# install time, not at commit time.).
#
# After running: Layer 1.5 + Layer 2 should pass via pre-commit on
# the next commit. This script does NOT run the gates itself —
# verify via `git commit` (any commit) or by invoking
# `files/.venv/bin/python files/tests/test_sm_derivation_ledger.py`
# directly.
#
# Shipped at C18 (2026-05-21). HANDOFF "Fresh-checkout setup"
# references this script.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    echo "ERROR: not inside a git repo. Run from the project root." >&2
    exit 1
fi

VENV_PYTHON="$REPO_ROOT/files/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    cat >&2 <<EOF
ERROR: project venv Python not found at:
  $VENV_PYTHON

The pre-commit hook needs Python 3.10+ (the project venv is 3.12).
System python3 on macOS is typically 3.9 and will fail Layer 1.5
with 'TypeError: unsupported operand type(s) for |: type and
NoneType' on eyes/agent.py imports (the C15 cross-field-pairing
gate test transitively imports eyes/agent.py via test_pipeline.py).

Set up the venv first:
  cd $REPO_ROOT/files
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt   # or project equivalent

Then re-run this script.
EOF
    exit 1
fi

HOOK_PATH="$REPO_ROOT/.git/hooks/pre-commit"
HOOK_DIR="$(dirname "$HOOK_PATH")"

if [ ! -d "$HOOK_DIR" ]; then
    echo "ERROR: $HOOK_DIR not present (no .git/hooks dir). Is this a fresh clone?" >&2
    exit 1
fi

cat > "$HOOK_PATH" <<'HOOK_EOF'
#!/bin/sh
# SM derivation ledger harness — pre-commit gate.
#
# Every commit on derive-not-detect must pass:
#   Layer 1.5: files/tests/test_sm_derivation_ledger.py
#     (36-ball ledger + 6 cross-field pairing cases per C15)
#   Layer 2:   files/tests/test_pipeline_captured_replay.py
#     (29-ball ledger-matched commits, real captured Scout dump
#     driving SM + scoreboard end-to-end)
#
# If either harness fails, block the commit.
# Bypass (rare, justified): git commit --no-verify
#
# Installed by scripts/setup_precommit.sh. Re-install after a
# fresh clone or after this content changes.

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HARNESS_L15="$REPO_ROOT/files/tests/test_sm_derivation_ledger.py"
HARNESS_L2="$REPO_ROOT/files/tests/test_pipeline_captured_replay.py"

# Prefer the project venv Python (3.12). C15 cross-field pairing
# test imports eyes/agent.py which uses Python 3.10+ syntax
# (`int | None`). System python3 on macOS is 3.9 and fails. The
# setup script (scripts/setup_precommit.sh) errors out if venv is
# missing, so by the time this hook runs the venv should be in
# place; the fallback is defensive.
PYBIN="python3"
if [ -x "$REPO_ROOT/files/.venv/bin/python" ]; then
    PYBIN="$REPO_ROOT/files/.venv/bin/python"
fi

if [ ! -f "$HARNESS_L15" ]; then
    echo "pre-commit: Layer 1.5 harness not found — skipping all gates"
    exit 0
fi

cd "$REPO_ROOT"

if "$PYBIN" "$HARNESS_L15" > /tmp/harness_l15_pre_commit.log 2>&1; then
    echo "pre-commit: Layer 1.5 PASS (36/36)"
else
    echo "pre-commit: Layer 1.5 FAILED — commit blocked"
    echo "--- last 30 lines of Layer 1.5 output ---"
    tail -30 /tmp/harness_l15_pre_commit.log
    echo "---"
    echo "Full log: /tmp/harness_l15_pre_commit.log"
    echo "Bypass (use sparingly): git commit --no-verify"
    exit 1
fi

if [ ! -f "$HARNESS_L2" ]; then
    echo "pre-commit: Layer 2 harness not found — skipping L2 gate"
    exit 0
fi

if "$PYBIN" "$HARNESS_L2" > /tmp/harness_l2_pre_commit.log 2>&1; then
    L2_PASS=$(grep -c "^PASS " /tmp/harness_l2_pre_commit.log || echo "?")
    echo "pre-commit: Layer 2 PASS ($L2_PASS balls)"
    exit 0
else
    echo "pre-commit: Layer 2 FAILED — commit blocked"
    echo "--- last 30 lines of Layer 2 output ---"
    tail -30 /tmp/harness_l2_pre_commit.log
    echo "---"
    echo "Full log: /tmp/harness_l2_pre_commit.log"
    echo "Bypass (use sparingly): git commit --no-verify"
    exit 1
fi
HOOK_EOF

chmod +x "$HOOK_PATH"

cat <<EOF
OK: pre-commit hook installed at:
  $HOOK_PATH

Hook uses project venv Python:
  $VENV_PYTHON

Verify Layer 1.5 + Layer 2 hold by either:
  (a) running any commit on the branch (the hook fires automatically), or
  (b) invoking the harnesses directly:
      $VENV_PYTHON $REPO_ROOT/files/tests/test_sm_derivation_ledger.py
      $VENV_PYTHON $REPO_ROOT/files/tests/test_pipeline_captured_replay.py
EOF
