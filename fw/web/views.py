"""A pericope's blocks as the page edits them: text, containers, pictures, expressions, and quotes with what they show
(and, when they can be written through, what their target holds, or a masked one's lens). Pure."""
from __future__ import annotations

from fw import store
from fw.web.common import MAX_DEPTH, blocks_of


def shown_text(text: str) -> str:
    """A masked view's text as the page shows it: each hidden stretch a …."""
    return text.replace(store.ELLIPSIS, "…").replace(store.CLOSE, "").replace(store.OPEN, "")


def links_json(library: dict, b: dict) -> list:
    return [{"to": l["to"], "at": l["at"], "title": library[l["to"]]["title"] if l["to"] in library else "gone"}
            for l in store.links(b)]


def para_json(library: dict, b: dict) -> dict | None:
    """What `b` paraphrases: its id, title, where it lives, its text."""
    src = store.paraphrases(b)
    if not src:
        return None
    if src not in library:
        return {"id": src, "title": "(its source is gone)", "text": "", "home": None}
    blocks = blocks_of(library)
    return {"id": src, "title": library[src]["title"], "text": store.full_text(blocks, src)[:4000],
            "home": store.home_of(blocks, src)[0]}


def text_json(library: dict, ref: str, b: dict, text: str, **more) -> dict:
    return {"t": "text", "id": ref, **more, "text": text, "links": links_json(library, b), "para": para_json(library, b)}


def items_json(library: dict, items: list, depth: int, path: tuple) -> list:
    """A quote's body (store.quote_items), read only."""
    def one(item):
        match item:
            case ("text", text):
                return {"t": "text", "text": shown_text(text)}
            case ("image", iid):
                return {"t": "image", "file": store.image_of(library.get(iid, {}).get("block"))}
            case ("expr", eid):
                return {"t": "expr", "source": store.expr_of(library.get(eid, {}).get("block")) or ""}
            case ("quote", target, mask, show, inner):
                return quote_json(library, None, target, mask, show, inner, depth + 1, path)
    return [x for x in map(one, items) if x is not None]


def editable(library: dict, target: str, mask, depth: int, path: tuple, locked: bool) -> bool:
    """A quote of `target` can be written through: unmasked, unlocked, no loop, within MAX_DEPTH, not a picture."""
    entry = library.get(target)
    return (entry is not None and mask is None and not locked and depth <= MAX_DEPTH and target not in path
            and not store.image_of(entry["block"]))


def tree_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> list:
    """What `ref` holds: its blocks; a block of text, its own text (`own`); a picture, the picture."""
    b = library[ref]["block"]
    if store.text_of(b) is not None:
        return [text_json(library, ref, b, store.text_of(b), own=True)]
    if store.image_of(b):
        return [{"t": "image", "id": None, "file": store.image_of(b)}]
    return [node_json(library, k, depth, path, locked) for k in store.children(b)]


def kept_json(library: dict, line: str, depth: int, path: tuple) -> dict | None:
    """A draft's quote or picture line, drawn read only."""
    if (q := store.QUOTE_RE.fullmatch(line)):
        qid, target = q.group(2), q.group(1)
        data = node_json(library, qid, depth, path) if qid in library else quote_json(library, None, target, None, [], {}, depth, path)
        for k in ("tree", "lens", "base"):
            data.pop(k, None)
        return data
    if (m := store.IMAGE_RE.fullmatch(line)):
        return {"t": "image", "file": store.image_of((library.get(m.group(1)) or {}).get("block"))}
    return None


def lens_json(library: dict, target: str, mask: list, depth: int = 1, path: tuple = ()) -> list:
    """A masked quote's view as segments: a block's text (`marker` kept exactly, `text` with ELLIPSIS holes), or a
    line kept as it is (`line`: a quote or picture inside, read only)."""
    out = []
    for line in store.view(store.block_draft(blocks_of(library), target), mask).split("\n"):
        if (m := store.BLOCK_RE.fullmatch(line)):
            out.append({"t": "text", "id": m.group(1), "marker": line, "lines": []})
        elif (q := store.QUOTE_RE.fullmatch(line)) or store.IMAGE_RE.fullmatch(line):
            title = (library.get(q.group(1)) or {}).get("title", "missing block") if q else "picture"
            out.append({"t": "line", "line": line, "title": title, "data": kept_json(library, line, depth + 1, path + (target,))})
        else:
            if not out or out[-1]["t"] != "text":
                out.append({"t": "text", "id": None, "marker": None, "lines": []})
            out[-1]["lines"].append(line)
    for seg in out:
        if seg["t"] == "text":
            seg["empty"] = not seg["lines"]
            seg["text"] = "\n".join(seg.pop("lines"))
    return out


def quoted_expr(blocks: dict, target: str) -> str | None:
    """The one expression a quote of `target` shows: `target`, or the only block it holds; else None."""
    b = blocks.get(target)
    if store.expr_of(b) is not None:
        return target
    kids = store.children(b) if b else []
    return kids[0] if len(kids) == 1 and store.expr_of(blocks.get(kids[0])) is not None else None


def quote_json(library: dict, qid: str | None, target: str, mask, show, inner, depth: int, path: tuple,
               locked: bool = False) -> dict:
    """A quote of `target` (its own block `qid`, if any), with what it shows; when it can be written through, what
    its target holds (`tree`) or its lens (`lens`), and its `base`."""
    blocks = blocks_of(library)
    entry = library.get(target)
    b = entry["block"] if entry else {}
    lock = bool(qid and store.quote_lock(blocks.get(qid)))
    locked = locked or lock
    q = {"t": "quote", "id": qid, "target": target, "title": entry["title"] if entry else "missing block",
         "home": store.home_of(blocks, target)[0] if entry else None,
         "masked": mask is not None, "show": list(show or []), "lock": lock, "locked": locked,
         "picture": bool(entry and store.image_of(b)),
         "created": b.get("created") if entry else None, "updated": b.get("updated") if entry else None,
         "words": b.get("words", 0) if entry else 0}
    if entry and (one := quoted_expr(blocks, target)):
        q["expr"] = {"id": one, "source": store.expr_of(blocks[one])}
    if entry is None:
        q["body"] = [{"t": "note", "text": f"missing block {target}"}]
    elif target in path:
        q["body"] = [{"t": "note", "text": f"↻ {entry['title']}"}]
    elif depth > MAX_DEPTH:
        q["body"] = [{"t": "note", "text": f"⋯ {entry['title']}"}]
    else:
        items = store.quote_items(blocks, target, mask, frozenset(), inner)
        q["body"] = items_json(library, items, depth, path + (target,)) or [{"t": "note", "text": "(empty)"}]
        if editable(library, target, mask, depth, path, locked):
            q["tree"] = tree_json(library, target, depth + 1, path + (target,), locked)
            q["base"] = store.content_hash(blocks, target)
        elif mask is not None and qid and editable(library, target, None, depth, path, locked):
            q["lens"] = lens_json(library, target, mask, depth, path)
            q["hole"] = store.ELLIPSIS
            q["base"] = store.content_hash(blocks, target)
    return q


def node_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> dict:
    """One block of a pericope. `path`: the blocks quoted on the way here; `locked`: inside a locked quote."""
    blocks = blocks_of(library)
    b = blocks[ref]
    if store.quoted(b):
        _, _, mask, show, inner = store.seen_quote(blocks, ref, {})
        return quote_json(library, ref, store.quoted(b)[0], mask, show, inner, depth, path, locked)
    if store.image_of(b):
        return {"t": "image", "id": ref, "file": store.image_of(b)}
    if store.expr_of(b) is not None:
        return {"t": "expr", "id": ref, "source": store.expr_of(b)}
    if (kids := store.children(b)):
        return {"t": "container", "id": ref, "children": [node_json(library, k, depth, path, locked) for k in kids]}
    return text_json(library, ref, b, store.own_text(blocks, ref))


def masking_json(library: dict, qid: str) -> dict:
    """What masking quote `qid` works on: its target's draft, the mask being edited, and the draft's lines, each
    with where it starts (marker lines left out: a line carries its block's id)."""
    blocks = blocks_of(library)
    target, mask = store.quoted(blocks[qid])
    draft = store.block_draft(blocks, target)
    lines, pos, block = [], 0, None
    for line in draft.split("\n"):
        if (m := store.BLOCK_RE.fullmatch(line)):
            block = m.group(1)
        elif (q := store.QUOTE_RE.fullmatch(line)):
            lines.append({"t": "quote", "start": pos, "end": pos + len(line),
                          "title": library[q.group(1)]["title"] if q.group(1) in library else "missing block",
                          "data": kept_json(library, line, 2, (target,))})
        elif store.IMAGE_RE.fullmatch(line):
            lines.append({"t": "picture", "start": pos, "end": pos + len(line), "data": kept_json(library, line, 2, (target,))})
        else:
            lines.append({"t": "text", "start": pos, "text": line, "block": block})
        pos += len(line) + 1
    return {"quote": qid, "target": target, "title": library[target]["title"], "draft": draft,
            "mask": store.edit_mask(draft, mask), "lines": lines}


MASK_OPS = {"wrap": lambda m, a, b, i, n: store.wrap(m, a, b), "minus": lambda m, a, b, i, n: store.minus(m, a, b),
            "open": lambda m, a, b, i, n: store.open_at(m, a, n), "close": lambda m, a, b, i, n: store.close_at(m, a, n),
            "drop": lambda m, a, b, i, n: store.drop_anchor(m, i, n)}


def mask_op(draft: str, mask: list, op: str, a: int = 0, b: int = 0, i: int = 0) -> list:
    """One key while masking: `[` on a..b shows it (wrap), `]` hides it (minus); at a point, open or close there;
    Backspace on bracket i drops it. The mask back, well formed."""
    return store.tidy_edit(draft, MASK_OPS[op](mask, a, b, i, len(draft)))
