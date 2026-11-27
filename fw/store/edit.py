"""Edits in place on the store being written (`data` and its index `blocks`): the steps every write is made of."""

from __future__ import annotations

import copy
from datetime import datetime

from fw.block import (
    block_draft, carry_links, children, image_of, index, links, loose, move_links, paraphrases, quote_inner,
    quoted, raw_mask, shown_text, subtree, text_of, with_children, with_inner, with_links, with_mask, with_text,
)
from fw.draft import new_id, now_local
from fw.lens import normalize, rebase


def new_block(bid: str, content, title=None, entry=False, links=(), *, now: datetime) -> dict:
    """A new block, made `now`."""
    now = now.isoformat(timespec="seconds")
    return with_links({"id": bid, "title": title, **({"entry": True} if entry else {}),
                       "content": content, "words": 0, "created": now, "updated": now}, list(links))


def add_block(data: dict, blocks: dict, bid: str, content, title=None, entry=False) -> dict:
    block = new_block(bid, content, title, entry, now=now_local())
    data["blocks"].append(block)
    blocks[bid] = block
    return block


def put_block(data: dict, blocks: dict | None, new: dict) -> dict:
    """Block `new` in its old one's place, by id (in `data` and its index `blocks`, if any). Returns it."""
    bid = new.get("id")
    old = blocks.get(bid) if blocks is not None else next((x for x in data["blocks"] if x.get("id") == bid), None)
    data["blocks"] = [new if x is old else x for x in data["blocks"]] if old is not None else [*data["blocks"], new]
    if blocks is not None:
        blocks[bid] = new
    return new


def marked(blocks: dict) -> set:
    """The paraphrases (kept even while empty: draft_items)."""
    return {i for i, b in blocks.items() if paraphrases(b)}


def fresh(blocks: dict, kids: list) -> str:
    return new_id(set(blocks) | set(kids))


def child_of(data: dict, blocks: dict, b: dict, mine: set, kids: list, item: tuple) -> list:
    """The ids of the child blocks that draft item `item` becomes in block `b` (made, or updated in place)."""
    kind = item[0]
    if kind == "quote":
        return [quote_block(data, blocks, b, item[1], item[2], kids)]
    if kind == "image":
        return image_block(data, blocks, b, item[1], kids)
    if kind == "blocks":
        cid = item[1] if item[1] in mine or loose(blocks, item[1]) else None
        return [set_container(data, blocks, cid, item[2], kids)]
    if kind == "expr":
        _, eid, src = item
        if eid in blocks and eid not in kids and (eid in mine or loose(blocks, eid)):
            put_block(data, blocks, {**blocks[eid], "content": {"expr": src}})
        else:
            eid = eid if eid not in blocks and eid not in kids else fresh(blocks, kids)
            add_block(data, blocks, eid, {"expr": src})
        return [eid]
    _, bid, text = item
    if bid in blocks and bid not in mine and not loose(blocks, bid):
        bid = new_id(blocks)  # another block's id: this text is a copy
    if bid in blocks:
        put_block(data, blocks, with_text(blocks[bid], text))  # (a paraphrase stays one)
    else:
        add_block(data, blocks, bid, text)
    return [bid]


def set_content(data: dict, blocks: dict, b: dict, items: list) -> None:
    """`items` (draft_items) made block `b`'s content: plain text while it's one run of text, else its children."""
    if text_of(b) is not None and all(i[0] == "text" for i in items) and len(items) <= 1:
        text = items[0][2] if items else ""
        put_block(data, blocks, with_text(with_links(b, move_links(text_of(b), text, links(b))), text))
        return
    mine, kids = set(children(b)), []
    for item in items:
        kids += child_of(data, blocks, b, mine, kids, item)
    put_block(data, blocks, with_children(b, kids))


def write_content(data: dict, blocks: dict, b: dict, items: list) -> None:
    """set_content, the links of the blocks in `b` carried along as one edit of its whole draft (carry_links)."""
    if text_of(b) is not None:
        return set_content(data, blocks, b, items)
    old = block_draft(blocks, b["id"])
    held = {i: links(blocks[i]) for i in subtree(blocks, b["id"]) if links(blocks.get(i))}
    set_content(data, blocks, b, items)
    for bid, ls in (carry_links(old, block_draft(blocks, b["id"]), held) if held else {}).items():
        if bid in blocks and text_of(blocks[bid]) is not None:
            put_block(data, blocks, with_links(blocks[bid], ls))


def set_container(data: dict, blocks: dict, cid: str | None, items: list, kids: list) -> str:
    """The child holding `items` (`cid`, or a new block); one run of text makes it plain text again. Returns its id."""
    if cid is None:
        cid = add_block(data, blocks, fresh(blocks, kids), "")["id"]
    c = blocks[cid]
    if len(items) == 1 and items[0][0] == "text":
        put_block(data, blocks, with_text(c, items[0][2]))
        return cid
    if text_of(c) is not None:
        c["content"] = []  # (its text, and its links, are in its children now)
        c.pop("links", None)
    set_content(data, blocks, c, items)
    return cid


def quote_block(data: dict, blocks: dict, b: dict, target: str, qid: str | None, kids: list) -> str:
    """The Quote block for a quote line in `b`: its own (or one nothing else holds) stays; one held elsewhere is copied."""
    old = blocks.get(qid) if qid else None
    q = quoted(old)
    held_elsewhere = q is not None and any(qid in children(x) for x in blocks.values() if x is not b)
    if q and qid not in kids and (qid in children(b) or not held_elsewhere):
        if q[0] != target:
            old["content"] = {"quote": target}  # pointed elsewhere: its mask no longer fits
        return qid
    nid = qid if qid and qid not in blocks else fresh(blocks, kids)
    add_block(data, blocks, nid, copy.deepcopy(old["content"]) if q and q[0] == target else {"quote": target})
    return nid


def image_block(data: dict, blocks: dict, b: dict, iid: str, kids: list) -> list:
    """The Image block for an image line in `b`, as a list of its id: its own or a loose one stays, else a copy."""
    name = image_of(blocks.get(iid))
    if name is None:
        return []
    if iid not in kids and (iid in children(b) or loose(blocks, iid)):
        return [iid]
    return [add_block(data, blocks, fresh(blocks, kids), {"image": name})["id"]]


def rebase_quotes(data: dict, ref: str, old: str, new: str, skip: str | None = None,
                  blocks: dict | None = None) -> dict:
    """Every quote of `ref`'s masks moved along with an edit of it, old → new (noted in data["rebased"]).
    Returns each quote moved, as it was before."""
    if old == new:
        return {}
    blocks, was = (index(data) if blocks is None else blocks), {}
    for b in data["blocks"]:
        q = quoted(b)
        if not q:
            continue
        before = copy.deepcopy(b)
        if q[0] == ref and q[1] is not None and b.get("id") != skip:
            b = put_block(data, blocks, with_mask(b, normalize(new, rebase(old, new, raw_mask(b)), keep_empty=True)))
            data.setdefault("rebased", set()).add(b.get("id"))
        inner = quote_inner(b)
        moved = {k: normalize(new, rebase(old, new, m)) for k, m in inner.items()
                 if (quoted(blocks.get(k)) or (None,))[0] == ref}
        if moved:
            b = put_block(data, blocks, with_inner(b, {**inner, **moved}))
            data.setdefault("rebased", set()).add(b.get("id"))
        if b != before:
            was[b["id"]] = before
    return was


def let_go(data: dict, blocks: dict, gone: set) -> dict | None:
    """Blocks `gone` (held by nothing): their quotes elsewhere keep what they showed, as text.
    Returns a record that puts them back, or None when nothing quoted them."""
    gone = {j for i in gone for j in subtree(blocks, i)}
    quotes = [b for b in data["blocks"] if quoted(b) and quoted(b)[0] in gone and b.get("id") not in gone]
    if not quotes:
        return None
    undo = {"blocks": {i: copy.deepcopy(blocks[i]) for i in gone} | {q["id"]: copy.deepcopy(q) for q in quotes}}
    for q in quotes:
        q["content"] = shown_text(blocks, q["id"])
    return undo
