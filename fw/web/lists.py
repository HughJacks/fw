"""The page's lists, a line per pericope: home, where to go from one, search, a kind's members. Pure but for the
model's guesses and the meaning service (fw.meaning), asked only when told to."""
from __future__ import annotations

from fw import meaning as fw_meaning
from fw import store
from fw.search import NEW, Search, blocks_inside, exits, home_order
from fw.web.common import blocks_of, entries, right, row


def minute() -> int:
    return int(store.clock() // 60)


def ask_meaning(text: str) -> list | None:
    """The meaning service's nearest blocks to `text`; None when it's off, the text is short, or it doesn't answer."""
    if fw_meaning.URL in ("", "off") or len(text.strip()) < fw_meaning.MIN_CHARS:
        return None
    try:
        return fw_meaning.fetch(fw_meaning.URL, text)
    except (OSError, ValueError):
        return None


def home_json(library: dict) -> list:
    """Every pericope in the recommendation's order (fw.search.home_order)."""
    blocks = blocks_of(library)
    return [row(library, blocks, i) for i in home_order(blocks, entries(library), minute())]


def exits_json(library: dict, here: str, meaning: bool = False) -> list:
    """Where to go from `here` (fw.search.exits); those filled from home's order `unrelated`."""
    blocks = blocks_of(library)
    refs = [r for r, e in library.items() if e["entry"]]
    near = ask_meaning(f"{library[here]['title']}\n{store.full_text(blocks, here)}"[:600]) if meaning else None
    related, filled = exits(blocks, refs, here, minute(), near)
    return [{**row(library, blocks, i), "unrelated": i in filled} for i in related + filled]


def search_json(library: dict, query: str, meaning: list | None = None) -> list:
    """Home's search: fw.search.Search's rows, the meaning service's answer mixed in when there is one. A paraphrase
    opens its original."""
    refs = entries(library)
    p = Search(library, refs, pinned=[(NEW, lambda q: f"+ new pericope “{q}”" if q else "+ new pericope")],
               inside=blocks_inside(library, refs))
    p.query = query
    if meaning is not None:
        p.meaning = (query, meaning)
    blocks = blocks_of(library)
    rows = []
    for key, shown, rt, *dim in p.rows():
        home = key if key == NEW or library[key]["entry"] else store.home_of(blocks, key)[0]
        go = key if key == NEW else p.source(key)
        orig = store.paraphrases(blocks.get(go))
        if orig in blocks and store.home_of(blocks, orig)[0]:
            home, go = store.home_of(blocks, orig)[0], orig
        rows.append({"key": "new" if key == NEW else key, "label": shown, "right": rt, "dim": bool(dim and dim[0]),
                     "open": home, "at": None if go in (NEW, home) else go,
                     "source": None if key == NEW else p.source(key),
                     "inside": key != NEW and key != home and not store.quoted(blocks.get(key))})
    return rows


def maybes_json(library: dict, kid: str) -> list:
    """A kind's maybes (store.maybes), likeliest first, each where it lives."""
    blocks = blocks_of(library)
    return [{"block": b, "home": store.home_of(blocks, b)[0], "title": library[b]["title"], "p": round(p, 2)}
            for b, p in store.maybes(store.load_guesses(), library, kid) if b in library]


def members_json(library: dict, kid: str) -> list:
    """A kind's members: your answers, then a model's sure guesses (`dim`, `p`), newest first; then its maybes
    (`maybe`), likeliest first. Each opens where it lives."""
    blocks = blocks_of(library)
    data = store.load_guesses()
    guesses = store.guessed(data, library)
    found = [b for b in reversed(store.of_kind(blocks, kid, guesses)) if b != kid and b in library]
    yours = [b for b in found if kid in store.kinds_of(blocks[b])]
    sure = [(b, guesses[b][kid]) for b in found if b not in yours]
    maybe = [(b, p) for b, p in store.maybes(data, library, kid) if b in library and b not in found]
    out = []
    for b, p, ask in [(b, None, False) for b in yours] + [(b, p, False) for b, p in sure] + [(b, p, True) for b, p in maybe]:
        home = store.home_of(blocks, b)[0]
        out.append({"key": b, "open": home, "title": library[b]["title"], "dim": p is not None,
                    **({"p": round(p, 2)} if p is not None else {}), **({"maybe": True} if ask else {}),
                    "right": right(library, b, home)})
    return out


def unkinded_json(library: dict) -> list:
    """The pericopes of no kind (no yes, no sure guess) that aren't kinds, newest first."""
    blocks = blocks_of(library)
    guesses = store.guessed(store.load_guesses(), library)
    none = [i for i, e in library.items() if e.get("entry") and store.kind_of(blocks.get(i)) is None
            and True not in store.merge_kinds(store.kinds_of(blocks.get(i)), guesses.get(i)).values()]
    return [{"key": b, "open": b, "title": library[b]["title"], "dim": False, "right": right(library, b)}
            for b in sorted(none, reverse=True)]


def kinds_json(library: dict, members: bool) -> dict:
    """Every kind {id, name}, oldest first; with `members`, each kind's, and `unkinded`."""
    if members:
        return {"kinds": [{"id": k, "name": library[k]["title"], "members": members_json(library, k)}
                          for k in store.kind_ids(library)], "unkinded": unkinded_json(library)}
    return {"kinds": [{"id": k, "name": library[k]["title"]} for k in store.kind_ids(library)]}
