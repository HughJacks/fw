"""Writes about quotes: through a masked view, masks, top lines, locks, detaching, popping out, nesting, deleting."""

from __future__ import annotations

import copy

from fw.block import (
    ancestors, block_draft, children, content_hash, cut_links, index, kind_of, kinds_of, links,
    mask_to, paraphrases, parents, quote_inner, quoted, raw_mask, shown_text, subtree, text_of, with_inner,
    with_kinds, with_links, with_lock, with_mask, with_show, with_visits,
)
from fw.draft import draft_items, new_id
from fw.lens import empties, normalize, put, rebase, with_empties
from fw.store.disk import load_data
from fw.store.edit import add_block, marked, put_block, rebase_quotes, write_content
from fw.store.paths import StoreError
from fw.store.write import editing, hashes, transact


def quote_of(blocks: dict, qid: str) -> tuple:
    q = quoted(blocks.get(qid))
    if q is None:
        raise StoreError(f"no quote {qid}")
    return q


def holders(ref: str) -> dict:
    """New content hashes of the blocks holding `ref`, as stored now."""
    data = load_data()
    return hashes(data, *parents(index(data), ref))


def on_quote(qid: str, edit) -> tuple:
    """`edit(data, blocks, target)` on quote `qid` in one write. Returns (its result, holders' hashes, an undo record)."""
    def change(data, blocks):
        target, _ = quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        return edit(data, blocks, target), undo
    result, undo = transact(editing(change))
    return result, holders(qid), undo


def masked(blocks: dict, qid: str, text: str, mask) -> dict:
    """Quote `qid` masked by `mask` (anchors into `text`, moved onto the stored text; None: all of it)."""
    stored = block_draft(blocks, quoted(blocks[qid])[0])
    return with_mask(blocks[qid], None if mask is None else
                     with_empties(normalize(stored, rebase(text, stored, mask)), empties(raw_mask(blocks[qid]))))


def set_quote_mask(qid: str, draft: str | None, mask: list | None, inner: bool = False) -> tuple[dict, dict]:
    """Quote `qid` masked (`mask`: anchors into `draft`; None shows all, and with `inner` its inner masks go too).
    Returns (holders' hashes, an undo record)."""
    def edit(data, blocks, target):
        put_block(data, blocks, masked(blocks, qid, draft, mask))
        if inner:
            put_block(data, blocks, with_inner(blocks[qid], {}))
    return on_quote(qid, edit)[1:]


def set_quote_masks(qid: str, own: tuple, inner: dict) -> tuple[dict, dict]:
    """Masking's result in one write: `own` = (text, mask) and inner masks {quote id: (text, mask or None)}."""
    def edit(data, blocks, target):
        put_block(data, blocks, masked(blocks, qid, *own))
        kept = dict(quote_inner(blocks[qid]))
        for iq, (draft, m) in inner.items():
            q = quoted(blocks.get(iq))
            if q is None or m is None:
                kept.pop(iq, None)
                continue
            st = block_draft(blocks, q[0])
            kept[iq] = normalize(st, rebase(draft, st, m))
        put_block(data, blocks, with_inner(blocks[qid], kept))
    return on_quote(qid, edit)[1:]


def mask_quote_to(qid: str, block: str) -> tuple[dict, dict]:
    """Quote `qid` masked to show just `block` (in what it quotes) and all it holds."""
    def edit(data, blocks, target):
        if block not in subtree(blocks, target):
            raise StoreError("that block isn't in what it quotes")
        draft = block_draft(blocks, target)
        put_block(data, blocks, with_mask(blocks[qid], normalize(draft, mask_to(blocks, target, draft, block))))
    return on_quote(qid, edit)[1:]


def set_quote_show(qid: str, show: list) -> tuple[dict, dict]:
    """Which of its target's properties quote `qid`'s top line shows."""
    return on_quote(qid, lambda data, blocks, _: put_block(data, blocks, with_show(blocks[qid], show)))[1:]


def set_quote_lock(qid: str, on: bool) -> tuple[dict, dict]:
    """Quote `qid` locked (nothing written through it) or unlocked."""
    return on_quote(qid, lambda data, blocks, _: put_block(data, blocks, with_lock(blocks[qid], on)))[1:]


def detach(qid: str) -> tuple[str, dict, dict]:
    """Quote `qid` turned into a plain copy of what it shows. Returns (that text, holders' hashes, an undo record)."""
    def edit(data, blocks, _):
        blocks[qid]["content"] = shown_text(blocks, qid)
        return blocks[qid]["content"]
    return on_quote(qid, edit)


def commit_view(qid: str, text: str, opened: int | None = None, base: str | None = None,
                seen: list | None = None, at: str | None = None) -> tuple[dict, dict]:
    """An edited view of masked quote `qid` saved into the block it shows (the lens's put), its mask moved along
    (`seen`: the mask quotes around it narrowed it to). Returns (hashes of that block and the quote's holders,
    the other quotes whose masks moved, as they were)."""
    moved = {}
    def change(data, blocks):
        target, mask = quote_of(blocks, qid)
        if base is not None and content_hash(blocks, target) != base:
            raise StoreError("not saved: this block changed in another session since you opened it")
        old = block_draft(blocks, target)
        narrowed = seen is not None and seen != mask
        draft, new_mask = put(old, seen if narrowed else mask, text, opened)
        write_content(data, blocks, blocks[target], draft_items(draft, blocks, marked(blocks)))
        stored = block_draft(blocks, target)
        if narrowed:
            moved.update(rebase_quotes(data, target, old, stored, blocks=blocks))
            moved.pop(qid, None)
            return target
        was = [x for t in empties(raw_mask(blocks[qid])) for x in (t, t)]  # its empty places, in hidden text
        new_mask = with_empties(new_mask, empties(rebase(old, draft, was)))
        put_block(data, blocks, with_mask(blocks[qid], normalize(stored, rebase(draft, stored, new_mask), keep_empty=True)))
        moved.update(rebase_quotes(data, target, old, stored, skip=qid, blocks=blocks))
        return target
    answer = lambda saved, target: hashes(saved, target, *parents(index(saved), qid))
    return transact(editing(change), answer=answer, at=at), moved


def _pop_out(data: dict, blocks: dict, ref: str) -> tuple[str, dict]:
    """pop_out's edit: (the new entry's id, an undo record)."""
    b = blocks.get(ref)
    if b is None or quoted(b):
        raise StoreError("that's a quote already" if b else "that block is gone")
    if kind_of(b) is not None:
        raise StoreError("a tag is a pericope of its own already")
    undo = {"blocks": {ref: copy.deepcopy(b)}}
    moved = new_id(blocks)
    put_block(data, blocks, with_links(add_block(data, blocks, moved, copy.deepcopy(b["content"])), links(b)))
    b.pop("links", None)
    put_block(data, blocks, with_visits(blocks[moved], b.pop("visits", None)))
    entry = add_block(data, blocks, new_id(blocks), [moved], entry=True)
    b["content"] = {"quote": entry["id"]}
    undo["blocks"].update({moved: None, entry["id"]: None})
    return entry["id"], undo


def pop_out(ref: str) -> tuple[str, dict, dict]:
    """Block `ref` (any content but a quote's) moved to a new entry of its own, quoted where it was.
    Returns (the entry's id, holders' hashes, an undo record)."""
    entry, undo = transact(editing(lambda data, blocks: _pop_out(data, blocks, ref)))
    return entry, holders(ref), undo


def new_entry(title: str | None, host: str) -> tuple[str, dict]:
    """A new, empty entry to be quoted in block `host`. Returns (its id, an undo record: it gone, `host` as now)."""
    def change(data, blocks):
        if host not in blocks:
            raise StoreError(f"no block with id {host}")
        undo = {"blocks": {host: copy.deepcopy(blocks[host])}}
        entry = add_block(data, blocks, new_id(blocks), [], title or None, entry=True)
        undo["blocks"][entry["id"]] = None
        return entry["id"], undo
    return transact(editing(change))


def nest_out(ref: str, before: str, middle: str, after: str) -> tuple[str, dict, dict]:
    """Part of text block `ref` (`middle`) made a quote of a new entry holding it, nested where it was (`ref` a
    container, or split in the one it's in). Returns (the entry's id, hashes of the blocks around it, an undo record)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or not isinstance(b.get("content"), str):
            raise StoreError("only text can be turned into a quote" if text_of(b) is None else "not inside a paraphrase: Turn into text first")
        outer = next((p for p in parents(blocks, ref) if not blocks[p].get("entry")), None)
        top = ancestors(blocks, ref)
        old = {t: block_draft(blocks, t) for t in top}
        undo = {"blocks": {i: copy.deepcopy(blocks[i]) for i in (ref, outer) if i}}
        for i, q in blocks.items():  # quotes of them: their masks move along
            if quoted(q) and quoted(q)[0] in top:
                undo["blocks"].setdefault(i, copy.deepcopy(q))
        text, ls = b["content"], links(b)
        at = text.find(middle, len(before))
        spans = {"before": (0, len(before)), "middle": (at, at + len(middle)), "after": (len(text) - len(after), len(text))}
        def new(content, piece=None, entry=False):
            block = add_block(data, blocks, new_id(blocks), content, entry=entry)
            if piece:
                block = put_block(data, blocks, with_links(block, cut_links(ls, *spans[piece])))
            undo["blocks"][block["id"]] = None
            return block["id"]
        entry = new([new(middle, "middle")], entry=True)
        quote = new({"quote": entry})
        if outer is None:
            b["content"] = ([new(before, "before")] if before else []) + [quote] + ([new(after, "after")] if after else [])
            b.pop("links", None)
        else:
            b["content"] = before
            put_block(data, blocks, with_links(b, cut_links(ls, *spans["before"])))
            kids = children(blocks[outer])
            i = kids.index(ref)
            kids[i:i + 1] = ([ref] if before else []) + [quote] + ([new(after, "after")] if after else [])
        for t in top:
            rebase_quotes(data, t, old[t], block_draft(blocks, t), blocks=blocks)
        return entry, top, undo
    entry, top, undo = transact(editing(change))
    return entry, hashes(load_data(), *top), undo


def delete_entry(eid: str) -> int:
    """Entry `eid` and all it holds erased; its quotes elsewhere keep what they showed, its links and paraphrases
    and answers about it go. Returns how many quotes kept text."""
    def change(data, blocks):
        if not blocks.get(eid, {}).get("entry"):
            raise StoreError(f"no pericope {eid}")
        gone, kept = set(subtree(blocks, eid)), 0
        for b in data["blocks"]:
            q = quoted(b)
            if q and q[0] in gone and b.get("id") not in gone:
                b["content"] = shown_text(blocks, b["id"])
                kept += 1
            b = put_block(data, blocks, with_links(b, [link for link in links(b) if link["to"] not in gone]))
            if paraphrases(b) in gone and b.get("id") not in gone:
                b = put_block(data, blocks, {**b, "content": text_of(b)})
            if any(k in gone for k in kinds_of(b)):
                put_block(data, blocks, with_kinds(b, {k: v for k, v in kinds_of(b).items() if k not in gone}))
        blocks[eid].pop("entry")  # (erased with what it holds when tidied)
        return kept
    return transact(editing(change))
