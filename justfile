# SportsComm project commands
#
# Graphify: explicit venv paths (override per machine via env).
# Option A — set GRAPHIFY_PYTHON / GRAPHIFY_EXE before `just`, or edit defaults.
#
# Agents: never invoke bare `graphify` — use `just graphify-parse` from repo root.
# See `.cursor/rules/graphify.mdc`.
GRAPHIFY_PYTHON := env_var_or_default("GRAPHIFY_PYTHON", "/Users/anmolmohan/Projects/graphify/.venv/bin/python")
GRAPHIFY_EXE := env_var_or_default("GRAPHIFY_EXE", "/Users/anmolmohan/Projects/graphify/.venv/bin/graphify")
REPOMIX := "/Users/anmolmohan/.local/node_modules/.bin/repomix"

# Default: list all commands
default:
    @just --list

# Run full recent-fixes suite (skips tests that need a working Groq SDK)
test:
    cd files && python test_recent_fixes.py

# Run recent-fixes suite including Groq client shape test (needs groq package + API key shape)
test-full:
    cd files && python test_recent_fixes.py --run-groq

# Pytest entry points (optional dev dependency `pytest`). Default skips Groq tests.
test-py:
    cd files && python -m pytest test_recent_fixes.py -v

test-py-full:
    cd files && python -m pytest test_recent_fixes.py --run-groq -v

# Run analyzer on most recent log
analyze:
    cd files && python analyze_match_telemetry.py \
        --log $(ls -t ../logs/pipeline-*.log | head -1) \
        --report-all-fixes --report-bundle-bc

# Run analyzer with all fix reports on specific log
analyze-log LOG:
    cd files && python analyze_match_telemetry.py \
        --log {{LOG}} \
        --report-all-fixes --report-bundle-bc

# Re-parse Graphify index (AST module + CLI; both refresh graphify-out/)
graphify-parse:
    cd files && {{GRAPHIFY_PYTHON}} -m graphify update .
    cd files && {{GRAPHIFY_EXE}} update .

# Watch for code changes and re-parse Graphify
graphify-watch:
    cd files && watchexec \
        --exts py \
        --watch . \
        --ignore "logs/**" \
        --ignore "debug_frames*/**" \
        --ignore "__pycache__/**" \
        --ignore ".graphify/**" \
        --ignore "graphify-out/**" \
        --debounce 2000 \
        -- sh -c '{{GRAPHIFY_PYTHON}} -m graphify update . && {{GRAPHIFY_EXE}} update .'

# Generate Repomix snapshot
repomix:
    {{REPOMIX}}

# Architecture-only Repomix (scoreboard + test_pipeline + score_manager)
repomix-arch:
    {{REPOMIX}} --config repomix.arch.config.json

# Tests-only Repomix
repomix-tests:
    {{REPOMIX}} --config repomix.tests.config.json

# Token count of a file
tokens FILE:
    @python -c "import tiktoken; enc = tiktoken.get_encoding('cl100k_base'); print(f'{len(enc.encode(open(\"{{FILE}}\").read())):,} tokens')"

# Token counts for the heaviest files
tokens-summary:
    @echo "Heaviest files by token count:"
    @just tokens files/test_pipeline.py
    @just tokens files/eyes/scoreboard.py
    @just tokens files/test_recent_fixes.py
    @just tokens files/score_manager.py
    @just tokens files/docs/backlog.md
    @just tokens files/analyze_match_telemetry.py

# Find callsites of a symbol (uses ripgrep)
find-calls SYMBOL:
    rg "{{SYMBOL}}\(" files/ --line-number --type python

# Find writes to a target pattern
find-writes PATTERN:
    sg --pattern '{{PATTERN}} = $_' --lang python files/

# Recent log analysis with watch
analyze-watch:
    cd files && watchexec --watch ../logs --exts log -- \
        python analyze_match_telemetry.py \
            --log $(ls -t ../logs/pipeline-*.log | head -1) \
            --report-all-fixes

# Quick file view with line numbers
show FILE LINES="":
    bat {{FILE}} {{LINES}}
