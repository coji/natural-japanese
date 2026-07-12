#!/usr/bin/env bash
# Sync the root skill sources (single source of truth) into skills/natural-japanese/
# for Claude Code plugin marketplace distribution.
#
# Copies to a temp directory first, then atomically replaces the destination
# with `mv` so a partial/interrupted run never leaves skills/ in a broken state.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/skills/natural-japanese"

TMP_DIR="$(mktemp -d "${REPO_ROOT}/.skill-sync.XXXXXX")"
trap 'rm -rf "${TMP_DIR}"' EXIT

mkdir -p "${TMP_DIR}/natural-japanese"

cp "${REPO_ROOT}/SKILL.md" "${TMP_DIR}/natural-japanese/SKILL.md"
cp -R "${REPO_ROOT}/references" "${TMP_DIR}/natural-japanese/references"

# Copy scripts/, excluding this sync script itself and __pycache__ noise.
mkdir -p "${TMP_DIR}/natural-japanese/scripts"
for entry in "${REPO_ROOT}"/scripts/*; do
  base="$(basename "${entry}")"
  case "${base}" in
    sync-skill.sh|__pycache__)
      continue
      ;;
  esac
  cp -R "${entry}" "${TMP_DIR}/natural-japanese/scripts/${base}"
done

cp -R "${REPO_ROOT}/assets" "${TMP_DIR}/natural-japanese/assets"

mkdir -p "${REPO_ROOT}/skills"
rm -rf "${DEST}.old"
if [ -d "${DEST}" ]; then
  mv "${DEST}" "${DEST}.old"
fi
mv "${TMP_DIR}/natural-japanese" "${DEST}"
rm -rf "${DEST}.old"

echo "synced: skills/natural-japanese/ <- SKILL.md, references/, scripts/, assets/"
