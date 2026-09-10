#!/usr/bin/env bash
set -euo pipefail

# Lightweight guard for accidental private keys and literal cloud credentials.
# Variable references such as `password = var.admin_password` are configuration,
# not secrets. Test fixtures and placeholder example files are excluded deliberately.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
git_repo=(git -C "$repo_root" -c "safe.directory=$repo_root")

secret_pathspec=(
  ':!*.md'
  ':!*.example'
  ':!tests/**'
  ':!scripts/preflight/check_no_secrets.sh'
)

if "${git_repo[@]}" grep -n -I -E \
  '(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|AccountKey=)' \
  -- "${secret_pathspec[@]}"; then
  echo 'Potential secret detected. Remove it before committing.' >&2
  exit 1
fi

if "${git_repo[@]}" grep -n -I -E \
  "(password|client_secret)[[:space:]]*[:=][[:space:]]*['\"][^'\"]+['\"]" \
  -- "${secret_pathspec[@]}"; then
  echo 'Potential secret detected. Remove it before committing.' >&2
  exit 1
fi
if "${git_repo[@]}" ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo '.env is tracked; remove it from Git.' >&2
  exit 1
fi
echo 'No obvious committed secrets detected.'
