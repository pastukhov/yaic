#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

output="$(poetry run python tools/publish_e2e_images.py \
  --source-id test \
  --dry-run)"

echo "$output" | grep -q "dry-run complete:"
