"""The store as the page hands it to the expression engine (TYPE.md): every pericope's title, kinds, facts and body
as stored. Pure."""
from __future__ import annotations

from datetime import datetime

from fw import store
from fw.web.common import blocks_of


def refs_of(b: dict) -> list:
    """What a block points at: a quote's target, its links', a paraphrase's source, its expressions' references."""
    q = store.quoted(b)
    p = store.paraphrases(b)
    return ([q[0]] if q else []) + [link["to"] for link in store.links(b)] + ([p] if p else []) + list(store.expr_refs(b))


def snap_node(blocks: dict, ref: str, seen: frozenset = frozenset()) -> dict:
    """Block `ref` as the engine reads it; one gone, or met again inside itself, unknown."""
    b = blocks.get(ref)
    if b is None or ref in seen:
        return {"id": ref, "t": "unknown"}
    if store.quoted(b):
        return {"id": ref, "t": "quote", "target": store.quoted(b)[0]}
    if store.paraphrases(b):
        return {"id": ref, "t": "paraphrase", "target": store.paraphrases(b), "text": store.text_of(b) or ""}
    if store.text_of(b) is not None:
        return {"id": ref, "t": "text", "text": store.text_of(b), "links": [{"to": l["to"], "at": list(l["at"])} for l in store.links(b)]}
    if store.image_of(b):
        return {"id": ref, "t": "picture", "target": ref}
    if store.expr_of(b) is not None:
        return {"id": ref, "t": "expr", "source": store.expr_of(b)}
    return {"id": ref, "t": "blocks", "children": [snap_node(blocks, k, seen | {ref}) for k in store.children(b)]}


def iso_minute(minute: int) -> str:
    return datetime.fromtimestamp(minute * 60).astimezone().isoformat(timespec="seconds")


def snapshot_json(library: dict) -> dict:
    """Every pericope and every block's facts (title, dates, visits, kinds, its pericope, the pericopes pointing at
    it, oldest first)."""
    blocks = blocks_of(library)
    up = {k: i for i, b in blocks.items() for k in store.children(b)}
    def home(i):
        seen = set()
        while i in up and i not in seen:
            seen.add(i)
            i = up[i]
        return i if i in library else None
    pointing = {}   # target -> [(created, the pericope pointing)]
    for i, b in blocks.items():
        if (targets := refs_of(b)) and (h := home(i)):
            for t in targets:
                pointing.setdefault(t, []).append((b.get("created") or "", h))
    def backs(i):
        return list(dict.fromkeys(h for _, h in sorted(pointing.get(i, [])) if h != i))
    def facts(i, b):
        v = b.get("visits") or {}
        return {"title": store.display_title(blocks, i) or "", "written": b.get("title"),
                "created": b.get("created") or "", "updated": b.get("updated") or "",
                "visits": v.get("total", 0), "first": iso_minute(v["first"]) if v.get("first") is not None else None,
                "recent": [[iso_minute(m), flags] for m, flags in v.get("recent") or []],
                "kinds": store.kinds_of(b) if b.get("entry") else {},
                "pericope": home(i) or i, "entry": bool(b.get("entry")), "backlinks": backs(i)}
    return {"now": datetime.now().astimezone().isoformat(timespec="seconds"),
            "facts": {i: facts(i, b) for i, b in blocks.items()},
            "pericopes": [{"id": i, "title": e["title"] or "",
                           "kinds": [k for k, yes in store.kinds_of(e["block"]).items() if yes],
                           "created": e["block"].get("created") or "", "updated": e["block"].get("updated") or "",
                           "visits": (e["block"].get("visits") or {}).get("total", 0),
                           "backlinks": backs(i), "body": snap_node(blocks, i)}
                          for i, e in library.items() if e["entry"]]}


def snapshot_part(library: dict, ids: set) -> dict:
    """Just what `ids` touch: the pericopes holding them, their facts and their pericopes', `gone` for the missing."""
    whole = snapshot_json(library)
    facts = whole["facts"]
    homes = {facts[i]["pericope"] for i in ids if i in facts}
    return {"pericopes": [p for p in whole["pericopes"] if p["id"] in homes or p["id"] in ids],
            "facts": {i: facts[i] for i in ids | homes if i in facts},
            "gone": sorted(i for i in ids if i not in facts)}
