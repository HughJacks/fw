"""Always the latest code: the page rebuilt when web/src changes, this core started again in place when fw's Python
changes (once no request is being answered). The page sees both through /api/version and reloads itself."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from fw import store

FW = Path(__file__).resolve().parent.parent
WEB = FW.parent / "web"

ACTIVE = [0]   # requests being answered now
ACTIVE_LOCK = threading.Lock()


def stamp_of(files) -> str:
    return hashlib.sha1("".join(f"{n}:{f.stat().st_size}:{f.stat().st_mtime_ns};" for n, f in files).encode()).hexdigest()[:12]


def code_stamp() -> str:
    """Which code this is: every fw/**/*.py, by path, size and time."""
    return stamp_of(sorted((str(f.relative_to(FW)), f) for f in FW.rglob("*.py")))


def page_stamp() -> str:
    """Which page is built: web/dist, by name, size and time."""
    return stamp_of(sorted((f.name, f) for f in (WEB / "dist").glob("*") if f.is_file()))


CODE = code_stamp()   # as it was when this one started


def page_stale() -> bool:
    """The page's source changed since it was last built."""
    built = WEB / "dist" / "app.js"
    if not built.exists():
        return True
    sources = [*(WEB / "src").rglob("*"), WEB / "build.mjs", WEB / "tailwind.config.js", WEB / "index.html"]
    return max((f.stat().st_mtime for f in sources if f.exists()), default=0) > built.stat().st_mtime


def build_page() -> bool:
    """node build.mjs, with whichever node there is (on PATH, else fnm's). Whether it built."""
    node = shutil.which("node")
    cmd = [node, "build.mjs"] if node else (["fnm", "exec", "--using=default", "node", "build.mjs"] if shutil.which("fnm") else None)
    return bool(cmd) and subprocess.run(cmd, cwd=WEB, capture_output=True, timeout=120).returncode == 0


def restart() -> None:
    """This core again, in place, as `python -m fw.web` with the same arguments."""
    print("fw web: fw's code changed; starting again", file=sys.stderr, flush=True)
    store.flush_json()
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(FW.parent), os.environ.get("PYTHONPATH")]))}
    os.execve(sys.executable, [sys.executable, "-m", "fw.web", *sys.argv[1:]], env)


def keep_current() -> None:
    while True:
        time.sleep(1)
        try:
            if page_stale():
                build_page()
            with ACTIVE_LOCK:
                idle = ACTIVE[0] == 0
            if idle and code_stamp() != CODE:
                restart()
        except (OSError, ValueError):
            continue
