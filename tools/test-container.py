"""Container entry point for test-in-container.sh; dependencies persist in /cache."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import venv


def main() -> None:
    root = Path('/work')
    cache = Path('/cache')
    fingerprint = hashlib.sha256()
    for name in ('pyproject.toml', 'poetry.lock'):
        fingerprint.update((root / name).read_bytes())
    fingerprint.update(sys.version.encode())
    fingerprint.update(sysconfig.get_platform().encode())
    fingerprint.update(platform.machine().encode())
    fingerprint.update(Path(__file__).read_bytes())
    environment = cache / 'envs' / fingerprint.hexdigest()[:24]
    python = environment / 'bin' / 'python'
    ready = environment / '.ready'
    os.environ['PIP_CACHE_DIR'] = str(cache / 'pip')
    if not ready.exists() or os.getenv('YAIC_TEST_REFRESH') == '1':
        ready.unlink(missing_ok=True)
        if not python.exists():
            venv.create(environment, with_pip=True)
        # Copy source into temporary build space: the worktree is read-only.
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            for name in ('pyproject.toml', 'README.md'):
                shutil.copy2(root / name, build / name)
            shutil.copytree(root / 'yaic', build / 'yaic')
            subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade',
                            str(build), 'pytest>=7.4,<8'], check=True)
        ready.write_text('Dependencies ready\n')
        print('Test dependencies installed in persistent mount', flush=True)
    else:
        print('Reusing test dependencies from persistent mount (no pip install)', flush=True)
    arguments = sys.argv[1:] or ['-q']
    raise SystemExit(subprocess.call([str(python), '-m', 'pytest',
                                     '-o', 'cache_dir=/cache/pytest', *arguments]))


if __name__ == '__main__':
    main()
