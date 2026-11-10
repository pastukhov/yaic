#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/docker" <<'FAKE'
#!/bin/sh
if [ "$1" = build ]; then
  touch "$TEST_DOCKER_BUILD"
  exit 0
fi
printf '%s\n' "$@" > "$TEST_DOCKER_ARGUMENTS"
python3 - "$@" <<'PYFAKE'
import pathlib, sys
mount = next(arg for arg in sys.argv[1:] if "target=/work,readonly" in arg)
source = pathlib.Path(mount.split("source=", 1)[1].split(",target=", 1)[0])
assert not (source / ".env").exists(), "checkout secrets must not be mounted"
assert (source / "yaic" / "config.py").exists()
assert (source / "tests").is_dir()
PYFAKE
FAKE
chmod +x "$work/docker"
mkdir -p "$work/source/tools" "$work/source/yaic" "$work/source/tests"
cp "$root/tools/test-in-container.sh" "$root/tools/Dockerfile.tests" "$work/source/tools/"
touch "$work/source/yaic/config.py" "$work/source/pyproject.toml" \
  "$work/source/poetry.lock" "$work/source/README.md"
printf 'synthetic-secret-for-test\n' > "$work/source/.env"
PATH="$work:$PATH" TEST_DOCKER_ARGUMENTS="$work/args" TEST_DOCKER_BUILD="$work/built" YAIC_TEST_CACHE="$work/cache with space" \
  "$work/source/tools/test-in-container.sh" tests/test_config.py -q
test -f "$work/built"
python3 - "$work/args" "$work/cache with space" <<'PY'
import pathlib, sys
args = pathlib.Path(sys.argv[1]).read_text().splitlines()
assert f'type=bind,source={sys.argv[2]},target=/cache' in args
assert args[-2:] == ['tests/test_config.py', '-q']
assert '--user' in args
assert '--env-file' not in args
assert not any('no-cache-dir' in arg for arg in args)
assert any('target=/work,readonly' in arg for arg in args)
PY
printf 'PASS: cache bind, read-only source, pytest arguments, no environment file\n'
