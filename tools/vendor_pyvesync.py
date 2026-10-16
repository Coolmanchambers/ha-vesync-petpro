"""Copy a pyvesync checkout into the integration as a private, relatively-imported package.

Usage:
  python vendor_pyvesync.py <pyvesync repo root> <custom_components/vesync_petpro dir>

The copy lives at <integration>/_pyvesync. Every `from pyvesync... import` is rewritten to a
relative import and the library's hard-coded 'pyvesync' logger name is replaced with the
vendored package name, so this copy never touches the `pyvesync` module that Home Assistant's
own vesync integration imports.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

FROM_IMPORT = re.compile(r'^(\s*)from pyvesync(\.[\w.]+)?(\s+import\b)', re.MULTILINE)
PLAIN_IMPORT = re.compile(r'^\s*import pyvesync\b', re.MULTILINE)
LOGGER_NAME = re.compile(r"logging\.getLogger\('pyvesync'\)")


def relative_prefix(path: Path, package_root: Path) -> str:
    depth = len(path.relative_to(package_root).parts) - 1
    return '.' * (depth + 1)


def rewrite(text: str, prefix: str) -> str:
    def repl(m: re.Match) -> str:
        indent, sub, tail = m.group(1), m.group(2) or '', m.group(3)
        target = prefix + sub.lstrip('.') if sub else prefix
        return f'{indent}from {target}{tail}'

    text = FROM_IMPORT.sub(repl, text)
    return LOGGER_NAME.sub("logging.getLogger(__name__.rsplit('.utils', 1)[0])", text)


def main(repo: Path, integration: Path) -> None:
    src = repo / 'src' / 'pyvesync'
    dest = integration / '_pyvesync'
    if not (src / '__init__.py').exists():
        raise SystemExit(f'not a pyvesync checkout: {src}')
    # Overwrite in place and delete only stale files: removing whole folders fails on
    # cloud-synced folders, which can hold a directory open.
    wanted = {
        f.relative_to(src)
        for f in src.rglob('*')
        if f.is_file() and '__pycache__' not in f.parts
    }
    if dest.exists():
        for old in dest.rglob('*'):
            if old.is_file() and old.relative_to(dest) not in wanted and old.name not in ('VENDORED.txt', 'LICENSE'):
                old.unlink()
    for file in sorted(src.rglob('*')):
        if '__pycache__' in file.parts or file.is_dir():
            continue
        out = dest / file.relative_to(src)
        out.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix == '.py':
            text = file.read_text(encoding='utf-8')
            out.write_text(rewrite(text, relative_prefix(file, src)), encoding='utf-8', newline='\n')
        else:
            shutil.copy2(file, out)

    leftovers = [
        f'{p.relative_to(dest)}:{n}'
        for p in dest.rglob('*.py')
        for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1)
        if re.match(r'\s*(from|import) pyvesync\b', line) or "getLogger('pyvesync')" in line
    ]
    if leftovers:
        raise SystemExit(f'absolute pyvesync references remain: {leftovers}')

    shutil.copy2(repo / 'LICENSE', dest / 'LICENSE')

    sha = subprocess.run(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True
    ).stdout.strip()
    branch = subprocess.run(
        ['git', '-C', str(repo), 'rev-parse', '--abbrev-ref', 'HEAD'],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    (dest / 'VENDORED.txt').write_text(
        'Vendored copy of pyvesync (MIT, see LICENSE in this folder) for vesync_petpro.\n'
        'Do not edit here: apply patches/*.patch to webdjoe/pyvesync dev 58eee3b, then run\n'
        'tools/vendor_pyvesync.py.\n'
        f'source: pyvesync PR #532 + Pet Pro/HA fixes, branch {branch}, commit {sha}\n',
        encoding='utf-8',
    )
    count = len(list(dest.rglob('*.py')))
    print(f'vendored {count} modules from {branch}@{sha[:7]} into {dest}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
