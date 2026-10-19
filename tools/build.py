"""Build the unchanged 4.137 source snapshot using an installed 1C Designer.

Copyright (C) 2026 Дмитрий Сушков
SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def metadata() -> dict:
    return json.loads((ROOT / 'tools/release.json').read_text(encoding='utf-8-sig'))


def verify_sources(info: dict) -> None:
    expected = info['sourceSHA256']
    actual = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (ROOT / 'src').rglob('*') if p.is_file()}
    changed = sorted(p for p in expected.keys() | actual.keys() if expected.get(p) != actual.get(p))
    if changed:
        raise ValueError('Sources differ from the 4.137 snapshot; see docs/BUILD.md: ' + ', '.join(changed))
    for path in (ROOT / 'src').rglob('*.xml'):
        ET.parse(path)
    print(f'SOURCE SNAPSHOT PASS: {len(actual)} files', flush=True)


def designer(executable: Path, base: Path, user: str, source: Path,
             output: Path, work: Path, label: str) -> None:
    log = work / (label + '.log')
    result = work / (label + '.result')
    command = [str(executable), 'DESIGNER', '/F', str(base)]
    if user:
        command += ['/N', user]
    command += ['/LoadExternalDataProcessorOrReportFromFiles', str(source), str(output),
                '/DisableStartupDialogs', '/Out', str(log), '/DumpResult', str(result)]
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    completed = subprocess.run(command, startupinfo=startup, timeout=120, check=False)
    result_code = result.read_text(encoding='utf-8-sig').strip() if result.exists() else None
    if completed.returncode != 0 or result_code != '0' or not output.is_file():
        raise RuntimeError(f'Designer failed for {label}; inspect {log} and {result}')
    print(f'BUILT: {label}', flush=True)


def build(args: argparse.Namespace, info: dict) -> Path:
    if sys.platform != 'win32':
        raise RuntimeError('This build launcher requires Windows and 1C Designer.')
    executable = args.designer.resolve(strict=True)
    base = args.base.resolve(strict=True)
    if not (base / '1Cv8.1CD').is_file():
        raise ValueError('Use a separate existing file test base with 1Cv8.1CD.')
    run_name = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    work = ROOT / '.build' / run_name
    work.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / 'src', work / 'src')
    main = info['main']
    for name in info['services']:
        binary = work / (name + '.epf')
        designer(executable, base, args.user, work / 'src' / (name + '.xml'), binary, work, name)
        template = work / 'src' / main / 'Templates' / info['templates'][name] / 'Ext/Template.bin'
        if not template.is_file():
            raise FileNotFoundError(template)
        shutil.copy2(binary, template)
    output = work / info['releaseFile']
    designer(executable, base, args.user, work / 'src' / (main + '.xml'), output, work, 'host')
    verify_sources(info)
    result = {'version': info['version'], 'buildId': info['buildId'],
              'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'officialReleaseSHA256': info['releaseSHA256'],
              'designerVersionNote': 'Compilation alone does not verify runtime behavior.'}
    (work / 'build-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('BUILD PASS: ' + str(output), flush=True)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify the source snapshot without launching 1C')
    parser.add_argument('--designer', type=Path, help='Absolute path to installed 1cv8.exe')
    parser.add_argument('--base', type=Path, help='Existing separate file test base, not a production base')
    parser.add_argument('--user', default='', help='Test-base user without a password; no production credentials')
    args = parser.parse_args()
    info = metadata()
    verify_sources(info)
    if not args.check:
        if args.designer is None or args.base is None:
            parser.error('--designer and --base are required for compilation')
        build(args, info)


if __name__ == '__main__':
    main()
