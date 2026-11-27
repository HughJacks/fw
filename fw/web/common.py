"""What every part of the core shares."""
from __future__ import annotations

import re

from fw import store

ID = r"\d{8}T\d{6}-[0-9a-f]{4}"
IMAGE_RE = re.compile(r"^[0-9a-f]+\.(png|jpg|jpeg|gif|webp)$")
MAX_DEPTH = store.MAX_DEPTH   # quotes inside quotes shown this deep, then a stand-in


def library() -> dict:
    return store.build_library(store.load_data())


def blocks_of(library: dict) -> dict:
    return {i: e["block"] for i, e in library.items()}


def entries(library: dict) -> list:
    """Every pericope's id, newest first."""
    return sorted((r for r, e in library.items() if e["entry"]), reverse=True)


def right(library: dict, i: str, words_of: str | None = None) -> str:
    """A list row's right column: MM/DD of `i`, and the words of `words_of` (default `i`)."""
    return f"{i[4:6]}/{i[6:8]}  {library[words_of or i].get('words', 0)}w"


def row(library: dict, blocks: dict, i: str) -> dict:
    """A pericope as home's list shows it."""
    return {"key": i, "title": library[i]["title"], "right": right(library, i), "kind": store.kind_of(blocks[i]) is not None}
