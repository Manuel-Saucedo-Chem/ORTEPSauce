"""Check for a newer ORTEPSauce and install it.

Where updates come from
  1. The latest GitHub release of GITHUB_REPO (tag such as v1.3.0). Assets used:
       *Windows*.zip  – the ORTEPSauce folder with ORTEPSauce.exe (for the .exe)
       the source zip of the tag (or an asset ORTEPSauce_V1.0.2.zip) – for the Python version
     GitHub publishes a SHA-256 digest for every asset; it is checked after downloading.
  2. Fallback: a JSON file on the web page (VERSION_URL):
       {"version": "1.3", "url": "<release page>", "notes": "…",
        "windows_zip": "<https url>", "windows_sha256": "…",
        "source_zip": "<https url>", "source_sha256": "…"}

What an update changes
  Only the program files. Your defaults, saved colors and the lab settings file live in your user
  folder (~/.ortepsauce.json), outside the program folder, so an update never touches them.
  .exe:   the new folder is copied over the old one by a small script that runs after ORTEPSauce
          closes, then ORTEPSauce starts again. _internal is replaced; other files you put next to
          the .exe are kept.
  Python: the ortepsauce package folder is replaced; the old one is kept as ortepsauce_backup_<ver>.
"""
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

from . import __version__

DOWNLOAD_PAGE = 'https://manuel-saucedo-chem.github.io/#programs'
GITHUB_REPO = 'Manuel-Saucedo-Chem/ORTEPSauce'
RELEASES_PAGE = f'https://github.com/{GITHUB_REPO}/releases/latest'
VERSION_URL = 'https://manuel-saucedo-chem.github.io/ortepsauce_version.json'
TIMEOUT = 8
# downloads are only accepted from these hosts (after redirects)
ALLOWED_HOSTS = ('github.com', 'api.github.com', 'codeload.github.com', 'objects.githubusercontent.com',
                 'release-assets.githubusercontent.com', 'github-releases.githubusercontent.com',
                 'manuel-saucedo-chem.github.io')
STATUS_PATH = os.path.join(os.path.expanduser('~'), '.ortepsauce_update.txt')
EXE_NAME = 'ORTEPSauce.exe'


class UpdateError(Exception):
    pass


# ---------------------------------------------------------------------------------------- versions
def parse_version(text):
    """'ORTEPSauce V1.10' -> (1, 10); 'v1.3.0' -> (1, 3, 0); unknown -> ()."""
    m = re.search(r'(\d+(?:\.\d+)*)', str(text or ''))
    return tuple(int(x) for x in m.group(1).split('.')) if m else ()


def is_newer(remote, local=__version__):
    r, l_ = parse_version(remote), parse_version(local)
    if not r:
        return False
    n = max(len(r), len(l_))
    return r + (0,) * (n - len(r)) > l_ + (0,) * (n - len(l_))


def short_version(v):
    """'1.3.0' -> '1.3' (the program's own style)."""
    p = list(parse_version(v))
    while len(p) > 2 and p[-1] == 0:
        p.pop()
    return '.'.join(str(x) for x in p) or str(v)


# ---------------------------------------------------------------------------------------- network
def _host_ok(url):
    u = urllib.parse.urlparse(url)
    host = (u.hostname or '').lower()
    return u.scheme == 'https' and (host in ALLOWED_HOSTS or host.endswith('.githubusercontent.com'))


def _open(url, accept='application/json'):
    if not _host_ok(url):
        raise UpdateError(f'Refusing to download from {url}')
    req = urllib.request.Request(url, headers={'User-Agent': f'ORTEPSauce/{__version__}', 'Accept': accept})
    try:
        ctx = ssl.create_default_context()
    except Exception:  # noqa: BLE001
        ctx = None
    r = urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx)
    if not _host_ok(r.geturl()):
        r.close()
        raise UpdateError(f'Redirected to an unexpected host: {r.geturl()}')
    return r


def _get_json(url):
    with _open(url) as r:
        return json.loads(r.read(1 << 20).decode('utf-8', 'replace'))


def _from_github():
    d = _get_json(f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest')
    tag = str(d.get('tag_name') or d.get('name') or '')
    if not tag:
        raise UpdateError('GitHub release without a tag')
    assets = {}
    for a in d.get('assets') or []:
        name = (a.get('name') or '').lower()
        url = a.get('browser_download_url')
        dig = str(a.get('digest') or '')
        sha = dig.split(':', 1)[1] if dig.startswith('sha256:') else None
        if not url or not name.endswith('.zip'):
            continue
        if 'windows' in name or 'win64' in name or '_exe' in name:
            assets['windows'] = (url, sha, a.get('size'))
        elif 'source' in name or re.match(r'ortepsauce_v[\d.]+\.zip$', name):
            assets.setdefault('source', (url, sha, a.get('size')))
    if 'source' not in assets and d.get('zipball_url'):
        assets['source'] = (d['zipball_url'], None, None)       # the code of the tag
    return dict(latest=short_version(tag), tag=tag, url=d.get('html_url') or RELEASES_PAGE,
                notes=(d.get('body') or '')[:3000], assets=assets, source='GitHub')


def _from_json():
    d = _get_json(VERSION_URL)
    v = str(d.get('version', ''))
    if not v:
        raise UpdateError('no version in the version file')
    assets = {}
    for kind in ('windows', 'source'):
        if d.get(f'{kind}_zip'):
            assets[kind] = (d[f'{kind}_zip'], d.get(f'{kind}_sha256'), None)
    return dict(latest=short_version(v), tag=v, url=d.get('url') or DOWNLOAD_PAGE, notes=d.get('notes', ''),
                assets=assets, source='web page')


def check_for_update():
    """dict(latest, url, notes, newer, assets{kind: (url, sha256|None, size|None)}) or raise."""
    err = None
    for fn in (_from_github, _from_json):
        try:
            res = fn()
            res['newer'] = is_newer(res['tag'])
            return res
        except Exception as e:  # noqa: BLE001
            err = e
    raise err or UpdateError('no version information found')


# ---------------------------------------------------------------------------------------- install
def install_kind():
    """'exe' (Windows .exe folder), 'source' (python -m ortepsauce) or None (cannot update in place)."""
    if getattr(sys, 'frozen', False):
        if sys.platform != 'win32':
            return None
        d = os.path.dirname(sys.executable)
        return 'exe' if _writable(d) else None
    pkg = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(pkg)
    return 'source' if _writable(pkg) and _writable(root) else None


def install_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(d):
    try:
        fd, p = tempfile.mkstemp(dir=d, prefix='.ortepsauce_write_test')
        os.close(fd)
        os.remove(p)
        return True
    except OSError:
        return False


def download(url, dest, sha256=None, progress=None, cancel=None):
    """Download url to dest (with progress(frac, msg)) and check the SHA-256 when known."""
    h = hashlib.sha256()
    with _open(url, accept='application/octet-stream') as r, open(dest, 'wb') as fh:
        total = int(r.headers.get('Content-Length') or 0)
        got = 0
        while True:
            if cancel is not None and cancel.is_set():
                raise UpdateError('Download cancelled')
            chunk = r.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress:
                mb = got / 1e6
                progress(0.05 + 0.75 * (got / total if total else min(0.9, mb / 150)),
                         f'Downloading update … {mb:.1f} MB' + (f' of {total / 1e6:.1f} MB' if total else ''))
    if sha256 and h.hexdigest().lower() != sha256.lower():
        os.remove(dest)
        raise UpdateError('The download is damaged (SHA-256 does not match). Nothing was changed.')
    return dest


def _safe_extract(zpath, dest):
    root = os.path.realpath(dest)
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = os.path.realpath(os.path.join(dest, m.filename))
            if not (target == root or target.startswith(root + os.sep)):
                raise UpdateError(f'Unsafe path in the update zip: {m.filename}')
        z.extractall(dest)


def _find(top, pred):
    for d, dirs, files in os.walk(top):
        if pred(d, files):
            return d
    return None


def _pkg_version(pkg_dir):
    try:
        with open(os.path.join(pkg_dir, '__init__.py'), encoding='utf-8') as fh:
            m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", fh.read())
        return m.group(1) if m else None
    except OSError:
        return None


def install_source(zpath, progress=None):
    """Replace the ortepsauce package folder. Returns dict(version, backup, requirements_changed)."""
    progress = progress or (lambda f, m='': None)
    pkg = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(pkg)
    tmp = tempfile.mkdtemp(prefix='ortepsauce_update_')
    try:
        progress(0.82, 'Unpacking …')
        _safe_extract(zpath, tmp)
        new_pkg = _find(tmp, lambda d, f: os.path.basename(d) == 'ortepsauce' and '__init__.py' in f
                        and 'gui.py' in f)
        if new_pkg is None:
            raise UpdateError('No ortepsauce folder in the downloaded file.')
        ver = _pkg_version(new_pkg)
        if not ver:
            raise UpdateError('The downloaded ortepsauce folder has no version number.')
        old_req = _read(os.path.join(pkg, 'requirements.txt'))
        new_req = _read(os.path.join(new_pkg, 'requirements.txt'))
        progress(0.9, 'Installing …')
        backup = os.path.join(root, f'ortepsauce_backup_{__version__}')
        if os.path.exists(backup):
            shutil.rmtree(backup, ignore_errors=True)
        for old in os.listdir(root):                       # keep only the newest backup
            if old.startswith('ortepsauce_backup_') and os.path.join(root, old) != backup:
                shutil.rmtree(os.path.join(root, old), ignore_errors=True)
        os.replace(pkg, backup)
        try:
            shutil.copytree(new_pkg, pkg, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        except Exception:
            if os.path.exists(pkg):
                shutil.rmtree(pkg, ignore_errors=True)
            os.replace(backup, pkg)                        # put the old version back
            raise
        # helper files next to the package (build_exe.bat, launcher, icon …)
        parent = os.path.dirname(new_pkg)
        for name in os.listdir(parent):
            src = os.path.join(parent, name)
            if os.path.isfile(src) and name.lower().endswith(('.bat', '.py', '.ico', '.png', '.md', '.txt', '.json')):
                try:
                    shutil.copy2(src, os.path.join(root, name))
                except OSError:
                    pass
        _write_status(f'OK {ver}')
        return dict(version=ver, backup=backup, requirements_changed=(old_req != new_req and bool(new_req)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _read(p):
    try:
        with open(p, encoding='utf-8') as fh:
            return fh.read().strip()
    except OSError:
        return ''


def pip_install_requirements():
    req = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', req], capture_output=True, text=True,
                       timeout=900)
    return r.returncode == 0, (r.stdout + r.stderr)[-2000:]


_BAT = r'''@echo off
chcp 65001 >nul
REM ORTEPSauce updater: waits for ORTEPSauce to close, copies the new version, starts it again.
set "PID={pid}"
set "SRC={src}"
set "DST={dst}"
set "STATUS={status}"
set /a N=0
:wait
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul
if errorlevel 1 goto copy
set /a N+=1
if %N% GEQ 120 goto fail
timeout /t 1 /nobreak >nul
goto wait
:copy
timeout /t 1 /nobreak >nul
if exist "%SRC%\_internal" (
  robocopy "%SRC%\_internal" "%DST%\_internal" /MIR /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 goto fail
)
robocopy "%SRC%" "%DST%" /E /XD "%SRC%\_internal" /R:5 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto fail
echo OK {version}> "%STATUS%"
start "" "%DST%\{exe}"
rmdir /s /q "{tmp}" >nul 2>&1
(goto) 2>nul & del "%~f0"
:fail
echo FAILED {version}> "%STATUS%"
start "" "%DST%\{exe}"
rmdir /s /q "{tmp}" >nul 2>&1
(goto) 2>nul & del "%~f0"
'''


def prepare_exe_update(zpath, version, progress=None):
    """Unpack the new .exe folder and write the updater script. Returns the script path; run it
    with launch_exe_update() and close ORTEPSauce."""
    progress = progress or (lambda f, m='': None)
    tmp = tempfile.mkdtemp(prefix='ortepsauce_update_')
    progress(0.85, 'Unpacking …')
    _safe_extract(zpath, tmp)
    src = _find(tmp, lambda d, f: EXE_NAME in f)
    if src is None:
        shutil.rmtree(tmp, ignore_errors=True)
        raise UpdateError(f'No {EXE_NAME} in the downloaded file.')
    bat = os.path.join(tempfile.gettempdir(), f'ortepsauce_update_{os.getpid()}.bat')   # outside tmp (deleted)
    with open(bat, 'w', encoding='utf-8', newline='\r\n') as fh:
        fh.write(_BAT.format(pid=os.getpid(), src=src, dst=install_dir(), status=STATUS_PATH,
                             version=version, exe=EXE_NAME, tmp=tmp))
    progress(0.95, 'Ready to install')
    return bat


def launch_exe_update(bat):
    flags = 0
    if sys.platform == 'win32':
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000      # CREATE_NO_WINDOW
    subprocess.Popen(['cmd', '/c', bat], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def restart_source(args=()):
    root = install_dir()
    subprocess.Popen([sys.executable, '-m', 'ortepsauce', *args], cwd=root, close_fds=True)


def _write_status(text):
    try:
        with open(STATUS_PATH, 'w', encoding='utf-8') as fh:
            fh.write(text)
    except OSError:
        pass


def pop_status():
    """Result of the last update ('OK 1.3' / 'FAILED 1.3') once, then forgotten."""
    try:
        with open(STATUS_PATH, encoding='utf-8', errors='replace') as fh:
            txt = fh.read().strip()
        os.remove(STATUS_PATH)
        return txt
    except OSError:
        return ''


def run_update(info, progress=None, cancel=None):
    """Download + install for this kind of installation. Returns dict(kind, version, ...)."""
    kind = install_kind()
    if kind is None:
        raise UpdateError('This copy of ORTEPSauce cannot update itself (folder not writable or not Windows). '
                          'Download the new version from the web page.')
    asset = info['assets'].get('windows' if kind == 'exe' else 'source')
    if not asset:
        raise UpdateError('This release has no ' + ('Windows .exe zip' if kind == 'exe' else 'source zip')
                          + ' to download. Please use the web page.')
    url, sha, _ = asset
    tmpd = tempfile.mkdtemp(prefix='ortepsauce_dl_')
    zpath = os.path.join(tmpd, 'update.zip')
    t0 = time.time()
    download(url, zpath, sha, progress, cancel)
    if kind == 'source':
        res = install_source(zpath, progress)
        shutil.rmtree(tmpd, ignore_errors=True)
        res['kind'] = 'source'
    else:
        bat = prepare_exe_update(zpath, info['latest'], progress)
        shutil.rmtree(tmpd, ignore_errors=True)            # unpacked already
        res = dict(kind='exe', version=info['latest'], bat=bat)
    res['verified'] = bool(sha)
    res['seconds'] = time.time() - t0
    return res
