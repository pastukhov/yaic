#!/usr/bin/env bash
# Persistent dependencies; no production environment or services are mounted.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cache=${YAIC_TEST_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/yaic-tests}
mkdir -p "$cache"
cache=$(cd "$cache" && pwd)
snapshot=$(mktemp -d)
trap 'rm -rf "$snapshot"' EXIT
python3 - "$root" "$snapshot" <<'PYTHON'
import pathlib
import shutil
import sys
source, target = map(pathlib.Path, sys.argv[1:])
ignore = shutil.ignore_patterns(".env*", "auth.json", "__pycache__", ".pytest_cache", ".venv", ".git")
for name in ("yaic", "tests", "tools"):
    shutil.copytree(source / name, target / name, ignore=ignore)
for name in ("pyproject.toml", "poetry.lock", "README.md"):
    shutil.copy2(source / name, target / name)
PYTHON
image=${YAIC_TEST_IMAGE:-yaic-tests:py312}
if [ -z "${YAIC_TEST_IMAGE:-}" ]; then
  docker build --file "$snapshot/tools/Dockerfile.tests" --tag "$image" "$snapshot"
fi
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$snapshot,target=/work,readonly" \
  --mount "type=bind,source=$cache,target=/cache" \
  --workdir /work \
  --env "YAIC_TEST_REFRESH=${YAIC_TEST_REFRESH:-0}" \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env PYTHONPATH=/work \
  "$image" \
  python /work/tools/test-container.py "$@"
