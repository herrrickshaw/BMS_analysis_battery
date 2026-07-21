#!/bin/bash
# lint.sh — run this repo's own bug-history rules.
# semgrep lives in the venv, not on PATH, and the ruleset is repo-relative —
# so both must be resolved here rather than remembered.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$HERE/.venv/bin/semgrep" --config "$HERE/.semgrep.yml" --metrics off "${@:-$HERE}"
