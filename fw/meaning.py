"""Search by meaning, asked of a search-by-meaning service. Nothing waits on it: when it
can't be reached the search is the title search. Standard library only.

    $FW_MEANING_URL   the service (default: off); empty or "off": never asked
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

URL = os.environ.get("FW_MEANING_URL", "")
TIMEOUT = 2.0     # seconds to wait for an answer
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
    """The block ids nearest `query`, nearest first; OSError or ValueError when there's no answer."""
    full = f"{url.rstrip('/')}/search?" + urllib.parse.urlencode({"q": query.strip(), "n": HOW_MANY})
    with urllib.request.urlopen(full, timeout=timeout) as r:
        return ids_of(json.loads(r.read().decode()))
