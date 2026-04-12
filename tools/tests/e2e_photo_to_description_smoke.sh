#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

output="$(poetry run python tools/e2e_photo_to_description.py \
  --source-id smoke \
  --dry-run)"

echo "$output" | grep -q "plan broker="
echo "$output" | grep -q "dry-run complete"
