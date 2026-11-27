"""The store's stamp, and which blocks changed between two stamps (the /api/live stream says both; the page patches
just those blocks)."""
from __future__ import annotations

import json
import threading
import time

from fw import store
from fw.web.common import blocks_of, library
from fw.web.snapshot import refs_of

TICK = 0.02   # s: how often a stream looks at the store (a stat)
QUIET = 15    # s: a comment sent this often on a quiet stream, so a dead page is noticed

LOCK = threading.Lock()
SEEN = {"stamp": None, "parts": {}, "refs": {}, "log": []}   # log: [(stamp, ids changed to reach it)], the last 64


def mtime(path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def stamp() -> int:
    """When the store last changed: its document, or the .json copy when something else wrote that."""
    return mtime(store.LORO_PATH) + (mtime(store.DATA_PATH) if store.json_changed() else 0)


def changed(was_parts: dict, was_refs: dict, parts: dict, refs: dict) -> set:
    """The blocks whose stored form differs, and what they point at, before and after. Pure."""
    out = {i for i in parts.keys() | was_parts.keys() if parts.get(i) != was_parts.get(i)}
    return out.union(*(refs.get(i, set()) | was_refs.get(i, set()) for i in out))


def look(now: int) -> None:
    """The log brought up to the store at stamp `now` (once, whichever stream asks)."""
    with LOCK:
        if SEEN["stamp"] == now:
            return
        blocks = blocks_of(library())
        parts = {i: json.dumps(b, sort_keys=True, default=str) for i, b in blocks.items()}
        refs = {i: set(refs_of(b)) for i, b in blocks.items()}
        ids = set() if SEEN["stamp"] is None else changed(SEEN["parts"], SEEN["refs"], parts, refs)
        SEEN.update(stamp=now, parts=parts, refs=refs, log=(SEEN["log"] + [(now, frozenset(ids))])[-64:])


def changed_since(last, now: int) -> list | None:
    """The ids changed from stamp `last` to `now`, or None when that's not known (then the page reads everything)."""
    look(now)
    with LOCK:
        stamps = [st for st, _ in SEEN["log"]]
        if last not in stamps or now not in stamps:
            return None
        return sorted(set().union(*(ids for _, ids in SEEN["log"][stamps.index(last) + 1: stamps.index(now) + 1])))


def stream(write) -> None:
    """Server-sent events to `write` until it fails: the stamp and what changed, at once and on every change."""
    write(b"retry: 300\n\n")
    last, quiet = None, 0.0
    while True:
        now = stamp()
        if now != last:
            write(f"data: {json.dumps({'stamp': now, 'changed': changed_since(last, now)})}\n\n".encode())
            last, quiet = now, 0.0
        elif quiet >= QUIET:
            write(b": \n\n")
            quiet = 0.0
        time.sleep(TICK)
        quiet += TICK
