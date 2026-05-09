#!/bin/bash
set -e

echo "=== Installing SportsComm token-optimization tooling ==="

# 1. Homebrew tools
echo "Installing Homebrew tools..."
brew install ripgrep fd bat ast-grep just watchexec

# 2. Python tools
echo "Installing Python tools..."
pip install tiktoken

# 3. Node tools
echo "Installing Node tools..."
npm install --prefix "$HOME/.local" repomix

# 4. Graphify
echo "Installing Graphify..."
cd ~/Projects
if [ ! -d "graphify" ]; then
    git clone https://github.com/safishamsi/graphify.git
fi
cd graphify
python3.12 -m venv .venv
".venv/bin/python" -m pip install -e .

# 5. Initial Graphify parse
echo "Parsing SportsComm codebase..."
cd /Users/anmolmohan/Projects/SportsComm/files
/Users/anmolmohan/Projects/graphify/.venv/bin/python -m graphify update .

# 6. Generate initial Repomix
echo "Generating initial Repomix snapshot..."
cd /Users/anmolmohan/Projects/SportsComm
"$HOME/.local/node_modules/.bin/repomix"

# 7. Install git pre-commit hook
echo "Installing git pre-commit hook..."
cat > /Users/anmolmohan/Projects/SportsComm/files/.git/hooks/pre-commit << 'HOOK_EOF'
#!/bin/bash
PYTHON_CHANGED=$(git diff --cached --name-only | grep '\.py$')
if [ -n "$PYTHON_CHANGED" ]; then
    echo "[graphify] Re-parsing graph..."
    cd "$(git rev-parse --show-toplevel)"
    /Users/anmolmohan/Projects/graphify/.venv/bin/python -m graphify update .
    [ $? -ne 0 ] && echo "[graphify] Parse failed; commit aborted." && exit 1
    echo "[graphify] Graph updated."
fi
exit 0
HOOK_EOF
chmod +x /Users/anmolmohan/Projects/SportsComm/files/.git/hooks/pre-commit

echo ""
echo "=== Installation complete ==="
echo ""
echo "Manual steps required:"
echo "1. Restart Cursor"
echo "2. Rebuild Cursor index after restart"
echo ""
echo "Verify with:"
echo "  just"
echo "  just tokens-summary"
echo "  just analyze (after a match)"
