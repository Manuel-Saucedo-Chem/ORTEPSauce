"""Makes the files for a GitHub release of ORTEPSauce (run by make_release.bat after building the .exe).

  ORTEPSauce_V<ver>_Windows.zip   the dist\\ORTEPSauce folder  -> used by the .exe's automatic update
  ORTEPSauce_V<ver>.zip           the Python version            -> used by the Python version's update
  ortepsauce_version.json         for the web page (fallback when GitHub cannot be reached)

Attach both zips to a new GitHub release with the tag v<ver>.0 (e.g. v1.3.0)."""
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ortepsauce import __version__ as VER  # noqa: E402
from ortepsauce.updates import GITHUB_REPO  # noqa: E402

TAG = f'v{VER}.0' if VER.count('.') == 1 else f'v{VER}'
HELPERS = ['build_exe.bat', 'make_release.bat', 'make_release.py', 'ortepsauce_launcher.py', 'make_icon.py',
           'ortepsauce.ico', 'icon_source.png']


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    os.chdir(HERE)
    out = {}
    dist = os.path.join('dist', 'ORTEPSauce')
    if os.path.exists(os.path.join(dist, 'ORTEPSauce.exe')):
        name = f'ORTEPSauce_V{VER}_Windows'
        shutil.make_archive(name, 'zip', 'dist', 'ORTEPSauce')
        out['windows'] = name + '.zip'
    else:
        print('No dist\\ORTEPSauce\\ORTEPSauce.exe - run build_exe.bat first (only the Python zip is made).')
    stage = tempfile.mkdtemp()
    top = os.path.join(stage, f'ORTEPSauce_V{VER}')
    shutil.copytree('ortepsauce', os.path.join(top, 'ortepsauce'),
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for f in HELPERS:
        if os.path.exists(f):
            shutil.copy2(f, top)
    name = f'ORTEPSauce_V{VER}'
    shutil.make_archive(name, 'zip', stage, f'ORTEPSauce_V{VER}')
    shutil.rmtree(stage, ignore_errors=True)
    out['source'] = name + '.zip'

    base = f'https://github.com/{GITHUB_REPO}/releases/download/{TAG}/'
    info = {'version': VER, 'url': f'https://github.com/{GITHUB_REPO}/releases/tag/{TAG}',
            'notes': f'ORTEPSauce {VER}'}
    print()
    for kind, f in out.items():
        h = sha256(f)
        info[f'{kind}_zip'] = base + f
        info[f'{kind}_sha256'] = h
        print(f'{f:<34} SHA-256 {h}')
    with open('ortepsauce_version.json', 'w', encoding='utf-8') as fh:
        json.dump(info, fh, indent=2)
    print('\nNext steps:')
    print(f'  1. GitHub -> {GITHUB_REPO} -> Releases -> "Draft a new release", tag {TAG}')
    print('  2. Attach: ' + ' and '.join(out.values()) + ', publish.')
    print('  3. (optional) Upload ortepsauce_version.json to your web page repository.')
    print('Every ORTEPSauce 1.0.1 or newer then finds the update and installs it from "Settings & updates".')


if __name__ == '__main__':
    main()
