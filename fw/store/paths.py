"""Where the store and what's kept beside it live, the lock, and whole-file writes."""

from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

FW = Path(__file__).resolve().parent.parent
ROOT = FW.parent
DATA_PATH = Path(os.environ.get("FW_DATA") or ROOT / "freewrites.json")  # the .json copy; FW_DATA: e.g. a test store
LOCK_PATH = DATA_PATH.with_name(".freewrites.lock")
LORO_PATH = DATA_PATH.with_suffix(".loro")             # the store itself, a Loro document
MIRROR_PATH = DATA_PATH.with_name(".freewrites.mirror")  # hash of the .json as last written from the document
PEER_PATH = DATA_PATH.with_name(".freewrites.peer")      # this machine's peer id in the document
CLIP_PATH = DATA_PATH.with_name(".fw-clip.json")         # the rich clipboard
IMAGES_PATH = DATA_PATH.with_name("images")              # Image blocks' pictures, named by their hash
TITLES_PATH = DATA_PATH.with_name("picture-titles.json")  # pictures' titles from a model
GUESSES_PATH = DATA_PATH.with_name("kind-guesses.json")   # a model's guesses at kinds
PROPOSALS_PATH = DATA_PATH.with_name("kind-proposals.json")  # kinds a model proposes
DISMISSED_PATH = DATA_PATH.with_name("kind-dismissed.json")  # proposals dismissed here
SCHEMA_PATH = FW / "schema.json"


class StoreError(Exception):
    """A write the store refused; the message says why."""


@contextmanager
def store_lock():
    """Held around every read-modify-write of the store, so writers take turns."""
    with open(LOCK_PATH, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def write_file(path: Path, data: bytes) -> None:
    """`data` into `path` whole or not at all (a temp file, then a rename), private."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".freewrites.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json_beside(path) -> dict:
    """A JSON object kept beside the store; {} when there's none or it can't be read."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def cached_json(path: Path, cache: list, read) -> dict:
    """`read(path)` kept in `cache` ([key, value]), read again only when the file changes; {} when there's none."""
    try:
        st = path.stat()
    except OSError:
        return {}
    if cache[0] != (st.st_mtime_ns, st.st_size):
        cache[:] = [(st.st_mtime_ns, st.st_size), read(path)]
    return cache[1]


def die(msg: str, code: int = 1):
    print(f"fw: {msg}", file=sys.stderr)
    sys.exit(code)
