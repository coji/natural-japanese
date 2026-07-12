#!/usr/bin/env bash
# Sync the root skill sources (single source of truth) into skills/natural-japanese/
# for Claude Code plugin marketplace distribution.
#
# Copies to a temp directory first (same filesystem as the destination, so the
# final swap is a cheap rename rather than a cross-device copy), then swaps it
# into place. NOTE: replacing an *existing* directory with another directory
# is not a single atomic filesystem operation on POSIX (there is no atomic
# "directory rename that also replaces a non-empty destination directory"),
# so this is a best-effort two-step swap (move old dir aside, move new dir
# in), guarded by a trap that restores the previous skills/natural-japanese/
# if the script is interrupted between those two steps.
#
# The backup path is suffixed with the PID ($$) so two concurrent runs of
# this script don't clobber each other's backup.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${REPO_ROOT}/skills/natural-japanese"
DEST_OLD="${DEST}.old.$$"

TMP_DIR="$(mktemp -d "${REPO_ROOT}/.skill-sync.XXXXXX")"

cleanup_and_restore() {
  local status=$?
  # If we got interrupted after moving DEST aside but before the final mv,
  # put the previous version back so skills/ is never left missing.
  if [ -d "${DEST_OLD}" ] && [ ! -d "${DEST}" ]; then
    echo "sync-skill.sh: interrupted mid-swap, restoring previous ${DEST} from ${DEST_OLD}" >&2
    mv "${DEST_OLD}" "${DEST}"
  fi
  rm -rf "${TMP_DIR}" "${DEST_OLD}"
  exit "${status}"
}
trap cleanup_and_restore EXIT

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
if [ -d "${DEST}" ]; then
  mv "${DEST}" "${DEST_OLD}"
fi
mv "${TMP_DIR}/natural-japanese" "${DEST}"

echo "synced: skills/natural-japanese/ <- SKILL.md, references/, scripts/, assets/"
