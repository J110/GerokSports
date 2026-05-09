---
description: Token optimization rules — applied to all requests
alwaysApply: true
---

# Token Optimization (Always Apply)

Output only what is necessary. Skip preamble, summaries, restated requests, and closing pleasantries. For code: show diff only, no surrounding context, no comments unless requested. For decisions: choice plus one-line rationale, no alternatives. For thinking: do not show extended reasoning output for tasks under 50 lines of change. For Composer: minimum changes only, no auto-improvements, max 5 tool calls per task, no auto-running tests or linters. Do not include open editors or current file unless @-mentioned. Do not read lockfiles, build artifacts, or generated content.
