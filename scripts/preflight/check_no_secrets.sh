#!/usr/bin/env bash
set -euo pipefail

# Lightweight guard for accidental private keys and common cloud secret names.
if git grep -n -I -E '(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|AccountKey=|password[[:space:]]*[:=]|client_secret[[:space:]]*[:=])' -- ':!*.md' ':!.env.example'; then
  echo 'Potential secret detected. Remove it before committing.' >&2
  exit 1
fi
if git ls-files --error-unmatch .env >/dev/null 2>&1; then
  echo '.env is tracked; remove it from Git.' >&2
  exit 1
fi
echo 'No obvious committed secrets detected.'
