"""What every write does to the whole store before it's saved: tidying, words, `updated`."""

from __future__ import annotations

from datetime import datetime

from fw.block import (
    children, entry_ids, full_text, index, picture_quote_id, pictures_held, quote_lock, quote_show, quoted,
    with_children, word_count,
)
from fw.store.edit import add_block, put_block


def pictures_apart(data: dict) -> int:
    """Every picture a block holds made a pericope of its own, a quote of it in its place. Returns how many."""
    blocks = index(data)
    held = pictures_held(blocks)
    for holder, pic in held:
        qid = picture_quote_id(pic, holder, {i for i, b in blocks.items() if quoted(b) != (pic, None)})
        if qid not in blocks:
            add_block(data, blocks, qid, {"quote": pic})
            blocks[qid]["created"] = blocks[pic].get("created", blocks[qid]["created"])
        put_block(data, blocks, with_children(blocks[holder], [qid if k == pic else k for k in children(blocks[holder])]))
        blocks[pic]["entry"] = True
    return len(held)


def kinds_apart(data: dict) -> int:
    """Only a pericope has kinds: a block inside one loses its answers. Returns how many."""
    inside = [b for b in data["blocks"] if "kinds" in b and not b.get("entry")]
    for b in inside:
        del b["kinds"]
    return len(inside)


def reached(blocks: dict, todo: list, seen: set) -> set:
    """Every block reached from `todo`, through children and quotes."""
    while todo:
        ref = todo.pop()
        if ref in seen or ref not in blocks:
            continue
        seen.add(ref)
        todo += children(blocks[ref]) + [q[0] for q in [quoted(blocks[ref])] if q]
    return seen


def collect(data: dict, keep=()) -> int:
    """Every block no entry (nor `keep`) reaches erased. Returns how many."""
    seen = reached(index(data), entry_ids(data) + list(keep), set())
    kept = [b for b in data["blocks"] if b.get("id") in seen]
    gone, data["blocks"] = len(data["blocks"]) - len(kept), kept
    return gone


def tidy_store(data: dict, keep=()) -> None:
    """Pictures and kinds kept to pericopes, then what nothing reaches erased."""
    pictures_apart(data)
    kinds_apart(data)
    collect(data, keep)


def sync_words(data: dict) -> bool:
    """Every block's words recounted, quoted text included. Returns whether any changed."""
    blocks, changed = index(data), False
    for b in data["blocks"]:
        words = word_count(full_text(blocks, b.get("id")))
        changed |= b.get("words") != words
        b["words"] = words
    return changed


def listed_once(data: dict) -> None:
    """After a merge, a block two containers list stays in the first by id (and once in it)."""
    seen = set()
    for b in sorted(data["blocks"], key=lambda b: b["id"]):
        kids = children(b)
        once = list(dict.fromkeys(kids))
        if kids and (any(k in seen for k in once) or once != kids):
            put_block(data, None, with_children(b, [k for k in once if k not in seen]))
        seen.update(kids)


def stamp_updated(data: dict, old_blocks: list, rebased: set, now: datetime) -> None:
    """`updated` = `now` on each block whose title or content changed since `old_blocks`, and on what holds it,
    up to its entry (not through quotes). Not changes: anchors moved along (`rebased`), words recounted.
    An `updated` the write set itself stays."""
    old, blocks = {b.get("id"): b for b in old_blocks}, index(data)
    parents = {}
    for b in data["blocks"]:
        for k in children(b):
            parents.setdefault(k, []).append(b.get("id"))
    kept = lambda i: old[i].get("updated") != blocks[i].get("updated")
    def changed(i):
        o, b = old[i], blocks[i]
        if i in rebased and quoted(o) and quoted(b) and quoted(o)[0] == quoted(b)[0]:
            return (quote_show(o), quote_lock(o)) != (quote_show(b), quote_lock(b))
        return (o.get("title"), o.get("content")) != (b.get("title"), b.get("content"))
    now = now.isoformat(timespec="seconds")
    todo, seen = [i for i in blocks if i in old and not kept(i) and changed(i)], set()
    while todo:
        i = todo.pop()
        if i in seen or i not in blocks:
            continue
        seen.add(i)
        if i not in old or not kept(i):
            blocks[i]["updated"] = now
        todo += parents.get(i, [])
    for b in data["blocks"]:
        b.setdefault("updated", b.get("created"))
