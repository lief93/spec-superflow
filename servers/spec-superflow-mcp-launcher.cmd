#!/bin/sh
:; if command -v node >/dev/null 2>&1; then exec node "$@"; fi; if [ -n "${SHELL:-}" ] && [ -x "$SHELL" ]; then exec "$SHELL" -lic 'exec node "$@" >&3' spec-superflow-mcp-launcher "$@" 3>&1 1>&2; fi; echo "Node.js 22 or newer was not found. Install Node.js and restart VS Code." >&2; exit 127
@echo off
where node >nul 2>&1
if errorlevel 1 (
  >&2 echo Node.js 22 or newer was not found. Install Node.js and restart VS Code.
  exit /b 127
)
node %*
exit /b %errorlevel%
