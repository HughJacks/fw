"""fw_meaning — search by meaning, asked of a search service, if you run one.

fw has no model of its own. A search service, run apart from fw, keeps an
embedding model loaded and answers which blocks are nearest a query:
GET <url>/search?q=…&n=… → {"results": [[block id, …], …]}, nearest first. fw asks it
after a pause in typing, in the background, and the search list mixes the
answer in by rank (fw_picker.fuse). Nothing waits on it: with none set, or
when it can't be reached, the search is the title search it always was, and
it isn't asked again for a while. Standard library only; the I/O is the
Asker's thread, the rest is pure.

    $FW_MEANING_URL   the service (default: none, never asked);
                      empty or "off": never asked (the tests set it so)
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

URL = os.environ.get("FW_MEANING_URL", "off")
PAUSE = 0.4       # seconds after the last key before asking
TIMEOUT = 2.0     # seconds to wait for an answer
RESTING = 60.0    # after a failure, seconds before asking again
MIN_CHARS = 3     # a query shorter than this isn't asked
HOW_MANY = 20


def ids_of(answer: dict) -> list:
    """The service's answer -> the block ids, nearest first."""
    out = []
    for r in (answer or {}).get("results") or []:
        if isinstance(r, list) and r and isinstance(r[0], str) and r[0] not in out:
            out.append(r[0])
    return out


def fetch(url: str, query: str, timeout: float = TIMEOUT) -> list:
    """The search service's answer for `query`: block ids, nearest first. Raises
    OSError or ValueError when there's none (down, slow, or nonsense)."""
    full = f"{url.rstrip('/')}/search?" + urllib.parse.urlencode({"q": query.strip(), "n": HOW_MANY})
    with urllib.request.urlopen(full, timeout=timeout) as r:
        return ids_of(json.loads(r.read().decode()))


class Asker:
    """One search list's questions to the search service: `want(query)` as you type,
    `tick()` when idle, which asks once the typing pauses and returns
    (query, block ids) when an answer comes for the query still wanted."""

    def __init__(self, url: str | None = None, clock=time.monotonic):
        self.url = (URL if url is None else url).rstrip("/")
        self.clock = clock
        self.query, self.since, self.asked = "", 0.0, None
        self.answer = None      # (query, ids) from the thread
        self.resting = 0.0      # no asking before this (the search service didn't answer)
        self.lock = threading.Lock()

    def on(self) -> bool:
        return bool(self.url) and self.url != "off"

    def want(self, query: str) -> None:
        if query != self.query:
            self.query, self.since = query, self.clock()

    def tick(self):
        now = self.clock()
        with self.lock:
            got, self.answer = self.answer, None
        if got and got[0] == self.query:
            return got
        q = self.query.strip()
        if (self.on() and len(q) >= MIN_CHARS and self.asked != self.query and now - self.since >= PAUSE
                and now >= self.resting):
            self.asked = self.query
            threading.Thread(target=self.ask, args=(self.query,), daemon=True).start()
        return None

    def ask(self, query: str) -> None:
        try:
            ids = fetch(self.url, query)
        except (OSError, ValueError):
            self.resting = self.clock() + RESTING
            return
        with self.lock:
            self.answer = (query, ids)
