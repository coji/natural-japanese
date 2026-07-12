#!/usr/bin/env bash
# Fixture regression check: verify scripts/lint.py detects the expected
# number of findings on the checked-in fixtures. Catches drift caused by
# lint rule changes or fixture edits (e.g. a fixture edit that accidentally
# introduces/removes a detectable pattern) before it lands in a commit or
# release.
#
# NOTE: If you intentionally change scripts/lint.py, scripts/textcore.py, or
# scripts/fixtures/, update the expected counts below to match.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LINT="${REPO_ROOT}/scripts/lint.py"
SMELLY_FIXTURE="${REPO_ROOT}/scripts/fixtures/ai-smelly.md"
NATURAL_FIXTURE="${REPO_ROOT}/scripts/fixtures/natural.md"

# Expected finding counts. Update these if you deliberately change the
# fixtures or the detector rules.
EXPECTED_SMELLY_DEFAULT=25
EXPECTED_SMELLY_EXPERIMENTAL=33
EXPECTED_NATURAL_DEFAULT=0
EXPECTED_NATURAL_EXPERIMENTAL=0

count_findings() {
  local file="$1"
  shift
  local json_out lint_status
  json_out="$(mktemp)"
  local cleanup_json_out="${json_out}"
  trap 'rm -f "${cleanup_json_out}"' RETURN

  set +e
  uv run "${LINT}" "${file}" --json "$@" >"${json_out}"
  lint_status=$?
  set -e

  if [ "${lint_status}" -ne 0 ]; then
    echo "error: lint run failed (exit=${lint_status}) for ${file} $*" >&2
    return 1
  fi

  local out py_status
  set +e
  out="$(python3 -c '
import json, sys
print(len(json.load(sys.stdin)["findings"]))
' <"${json_out}")"
  py_status=$?
  set -e

  if [ "${py_status}" -ne 0 ]; then
    echo "error: failed to parse lint JSON output (exit=${py_status}) for ${file} $*" >&2
    return 1
  fi

  echo "${out}"
}

fail=0

check() {
  local label="$1" expected="$2" actual="$3"
  case "${actual}" in
    ''|*[!0-9]*)
      echo "FAIL: ${label}: could not determine actual finding count (got '${actual}')" >&2
      fail=1
      return
      ;;
  esac
  if [ "${actual}" -ne "${expected}" ]; then
    echo "FAIL: ${label}: expected ${expected} findings, got ${actual} (diff: $((actual - expected)))" >&2
    fail=1
  else
    echo "OK: ${label}: ${actual} findings"
  fi
}

check "ai-smelly.md (default)" "${EXPECTED_SMELLY_DEFAULT}" "$(count_findings "${SMELLY_FIXTURE}")"
check "ai-smelly.md (--experimental)" "${EXPECTED_SMELLY_EXPERIMENTAL}" "$(count_findings "${SMELLY_FIXTURE}" --experimental)"
check "natural.md (default)" "${EXPECTED_NATURAL_DEFAULT}" "$(count_findings "${NATURAL_FIXTURE}")"
check "natural.md (--experimental)" "${EXPECTED_NATURAL_EXPERIMENTAL}" "$(count_findings "${NATURAL_FIXTURE}" --experimental)"

if [ "${fail}" -ne 0 ]; then
  echo "Fixture regression check FAILED." >&2
  exit 1
fi

echo "Fixture regression check PASSED."
