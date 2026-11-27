"""Attention from the page, kept as visits (store.attend) and written when they end (store.record_visits)."""
from __future__ import annotations

import threading
import time

from fw import store

VISITS = {"live": {}, "pending": {}}   # the visits under way, and those waiting to be written
LOCK = threading.Lock()


def attention(blocks: dict, pericope: str | None, block: str | None, flags: str, at: float) -> None:
    """On the pericope open ("o"); on the block the cursor's in, with `flags` (c, w, q), carried up to its pericope."""
    with LOCK:
        for ids, f in (([pericope], "o") if pericope else ([], ""),
                       ([block, *store.ancestors(blocks, block)], flags) if block and flags else ([], "")):
            if (ids := [i for i in ids if i in blocks]):
                VISITS["live"], seen = store.attend(VISITS["live"], ids, f, at)
                VISITS["pending"] = store.note_visits(VISITS["pending"], seen)


def flush_visits(everything: bool = False) -> None:
    """The visits that have ended, or all of them, written; kept to try again if the store refuses."""
    with LOCK:
        now = store.clock()
        if not VISITS["pending"] or not (everything or store.ended(VISITS["live"], now) & VISITS["pending"].keys()):
            return
        try:
            store.record_visits(VISITS["pending"])
        except (store.StoreError, OSError):
            return
        VISITS["pending"] = {}
        VISITS["live"] = {i: x for i, x in VISITS["live"].items() if now - x[1] <= store.VISIT_GAP}


def keep_flushing() -> None:
    while True:
        time.sleep(30)
        flush_visits()
