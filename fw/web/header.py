"""A pericope as the page opens it: its header (kinds, backlinks, a kind's members) and what it holds."""
from __future__ import annotations

from fw import store
from fw.web.common import blocks_of
from fw.web.lists import maybes_json, members_json
from fw.web.views import tree_json


def kind_tokens(library: dict, ref: str) -> list:
    """The kinds line: each answer (yes/no), then the guesses that count, `applied` or `guess`."""
    b = library[ref]["block"]
    out = [{"kind": k, "name": library[k]["title"], "mark": "yes" if yes else "no"}
           for k, yes in store.kinds_of(b).items() if store.kind_of(library.get(k, {}).get("block")) is not None]
    data = store.load_guesses()
    auto = store.learned(data)
    return out + [{"kind": k, "name": library[k]["title"], "p": round(p, 2),
                   "mark": "applied" if store.is_applied(library, ref, k, auto) else "guess"}
                  for k, p in store.guessed(data, library).get(ref, {}).items()]


def near_text(blocks: dict, up: dict, i: str) -> str:
    """The words beside block `i`: the block of text before it, else after."""
    kids = store.children(blocks.get(up.get(i), {})) or []
    n = kids.index(i) if i in kids else -1
    for k in ([kids[n - 1]] if n > 0 else []) + kids[n + 1:n + 2]:
        t = store.own_text(blocks, k).strip()
        if t and not store.quoted(blocks[k]):
            return t
    return ""


def link_text(blocks: dict, by: str, at: int) -> str:
    """The words around a link at `at` (an offset in its pericope) in block `by`."""
    own = store.own_text(blocks, by)
    spot = next((link["at"] for link in store.links(blocks[by]) if link["at"][0] == at - store.home_of(blocks, by)[1]), None)
    a, e = spot or (0, 0)
    return ("…" if a > 40 else "") + own[max(0, a - 40):e + 40].strip() + ("…" if e + 40 < len(own) else "")


def backlink_rows(library: dict, found: list) -> list:
    """The backlinks above the header, oldest first (a kind's members are below it instead): {key, open, at, title,
    kind, right: MM/DD, words around it}."""
    blocks = blocks_of(library)
    up = {k: i for i, b in blocks.items() for k in store.children(b)}
    out = []
    for x in found:
        if x["kind"] == "kind" or x["home"] not in library:
            continue
        by = x["by"]
        text = (link_text(blocks, by, x["at"]) if x["kind"] == "link" else
                store.text_of(blocks[by]) if x["kind"] == "paraphrase" else near_text(blocks, up, by))
        when = x["created"] or blocks[x["home"]].get("created") or ""
        out.append({"key": f"{x['kind']}:{by}:{x['at']}", "open": x["home"], "at": by, "title": library[x["home"]]["title"],
                    "kind": x["kind"], "right": f"{when[5:7]}/{when[8:10]}" if when else "",
                    "words": " ".join(text.split())[:120]})
    return out


def pericope_json(library: dict, ref: str) -> dict:
    blocks = blocks_of(library)
    b = blocks[ref]
    found = store.backlinks(blocks, ref)
    kind = store.kind_of(b) is not None
    return {"id": ref, "title": b.get("title"), "shown": library[ref]["title"],
            "type": store.type_label(b, blocks), "kind": kind,
            "created": b.get("created"), "updated": b.get("updated"), "words": b.get("words", 0),
            "visited": store.minute_iso(store.last_visit(b)) or None,
            "kinds": store.kinds_text(blocks, b), "kindTokens": kind_tokens(library, ref),
            "maybes": maybes_json(library, ref) if kind else None,
            "members": members_json(library, ref) if kind else None,
            "backlinks": store.backlink_summary(found) if found else "",
            "backlinkRows": backlink_rows(library, found),
            "base": store.content_hash(blocks, ref), "children": tree_json(library, ref, 1, (ref,))}
