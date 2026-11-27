"""Writes about text: hyperlinks and paraphrases."""

from __future__ import annotations

import copy

from fw.block import children, links, move_span, parents, quoted, text_of, with_children, with_links
from fw.draft import new_id, now_local
from fw.store.edit import add_block, put_block
from fw.store.paths import StoreError
from fw.store.quotes import _pop_out
from fw.store.write import editing, transact


def new_link(to: str, at: list) -> dict:
    """A hyperlink made now."""
    return {"to": to, "at": at, "created": now_local().isoformat(timespec="seconds")}


def on_text(ref: str, edit, missing: str = "only text can be linked"):
    """`edit(data, blocks, b, undo)` on text block `ref` in one write; returns its result (or the undo record)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or text_of(b) is None:
            raise StoreError(missing)
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        return edit(data, blocks, b, undo) or undo
    return transact(editing(change))


def link_text(ref: str, text: str, span: list, to: str | None, title: str | None = None) -> tuple[str, dict]:
    """Span `span` of `text` (block `ref`'s, as the editor has it) linked to entry `to`, or a new entry titled `title`.
    Returns (the entry linked to, an undo record)."""
    def edit(data, blocks, b, undo):
        target = to
        if target is None:
            target = add_block(data, blocks, new_id(blocks), [], title or None, entry=True)["id"]
            undo["blocks"][target] = None
        elif not blocks.get(target, {}).get("entry"):
            raise StoreError("that pericope is gone")
        at = move_span(text, text_of(b), span)
        kept = [link for link in links(b) if not (link["at"][0] < at[1] and link["at"][1] > at[0])]
        put_block(data, blocks, with_links(b, sorted(kept + [new_link(target, at)], key=lambda link: link["at"])))
        return target, undo
    return on_text(ref, edit)


def add_links(ref: str, text: str, new: list) -> dict:
    """Text block `ref` given links `new` (spans of `text`; links to entries gone left out), as a paste brings them."""
    def edit(data, blocks, b, undo):
        added = [new_link(link["to"], move_span(text, text_of(b), link["at"])) for link in new
                 if blocks.get(link["to"], {}).get("entry")]
        put_block(data, blocks, with_links(b, sorted(links(b) + added, key=lambda link: link["at"])))
    return on_text(ref, edit)


def unlink_text(ref: str, to: str, at: list) -> dict:
    """The link to `to` at `at` removed from block `ref`. Returns an undo record."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError(f"no block with id {ref}")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        put_block(data, blocks, with_links(b, [link for link in links(b) if not (link["to"] == to and link["at"] == at)]))
        return undo
    return transact(editing(change))


def _paraphrase_of(data: dict, blocks: dict, source: str) -> str:
    """A new, empty paraphrase of `source`, loose: its id."""
    if source not in blocks:
        raise StoreError("that block is gone")
    pid = new_id(blocks)
    add_block(data, blocks, pid, {"paraphrase": source, "text": ""})
    return pid


def new_paraphrase(source: str, record: dict | None = None) -> tuple[str, dict]:
    """A new, empty paraphrase of `source`, loose (the save listing it takes it in). Returns (its id, an undo record,
    merged into `record`)."""
    pid = transact(editing(lambda data, blocks: _paraphrase_of(data, blocks, source)), tidy=False)
    return pid, {"blocks": {pid: None, **((record or {}).get("blocks", {}))}}


def paraphrase_it(ref: str) -> tuple[str, dict]:
    """An empty paraphrase in `ref`'s place: of what quote `ref` quotes, or of `ref` popped out to a pericope of its
    own. One write. Returns (its id, an undo record)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError("write something first")
        source, record = (quoted(b)[0], None) if quoted(b) else _pop_out(data, blocks, ref)
        pid = _paraphrase_of(data, blocks, source)
        undo = {"blocks": {pid: None, **((record or {}).get("blocks", {}))}}
        for holder in parents(blocks, ref):
            undo["blocks"].setdefault(holder, copy.deepcopy(blocks[holder]))
            put_block(data, blocks, with_children(blocks[holder], [pid if k == ref else k for k in children(blocks[holder])]))
        undo["blocks"].setdefault(ref, copy.deepcopy(blocks[ref]))
        return pid, undo
    return transact(editing(change))


def set_paraphrase(ref: str, source: str | None) -> dict:
    """Text block `ref` (inside a pericope) made a paraphrase of `source`, its words kept (None: plain text again).
    Returns an undo record."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError("that block isn't saved yet: write something first")
        if text_of(b) is None:
            raise StoreError("only a block of text can be a paraphrase")
        if source is not None and b.get("entry"):
            raise StoreError("a pericope can't be a paraphrase: a paraphrase is a block inside one")
        if source is not None and source not in blocks:
            raise StoreError("that block is gone")
        if source == ref:
            raise StoreError("a block can't paraphrase itself")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        put_block(data, blocks, {**b, "content": {"paraphrase": source, "text": text_of(b)} if source else text_of(b)})
        return undo
    return transact(editing(change))
