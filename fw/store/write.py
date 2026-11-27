"""Every write in one shape (transact), and the editor's save of a block (commit), undo (restore), merging."""

from __future__ import annotations

import copy
import threading
from pathlib import Path

from fw import loro as fw_loro
from fw.block import (
    block_draft, content_hash, held, index, is_empty_untitled, kind_of, loose, masks_in,
    merge_visits, subtree, with_visits,
)
from fw.draft import draft_items, new_id, now_local
from fw.migrate import SCHEMA_VERSION, upgrade
from fw.store.clipboard import clip_holds
from fw.store.disk import (
    current_version, document, forget, json_changed, load_data, load_store, on_disk_read, peer, prepared,
    save_data, save_doc, write_doc,
)
from fw.store.edit import let_go, marked, rebase_quotes, write_content
from fw.store.paths import DATA_PATH, LORO_PATH, StoreError, store_lock
from fw.store.schema import _type_ok, editable_keys, invalid, load_schema
from fw.store.tidy import listed_once, stamp_updated, sync_words, tidy_store

_written = threading.local()


def written_version() -> str | None:
    """The version this thread's last transact wrote: the writer's own view (after a merge, its edits on what it saw)."""
    return getattr(_written, "version", None)


def finished(new: dict, tidy: bool, schema: dict, old: dict | None = None) -> dict:
    """A new store tidied (if `tidy`), its words recounted, validated (only what differs from `old`, if given)."""
    if tidy:
        tidy_store(new, clip_holds())
    sync_words(new)
    errs = invalid(new, schema, old)
    if errs:
        raise StoreError("refusing to save, a block became invalid: " + "; ".join(errs))
    return new


def transact(change, tidy: bool = True, answer=None, at: str | None = None):
    """One write, under the lock: `change(store)` → (new store, result[, rebased quotes]) (never changing the store
    it's given); the new store finished and saved. Returns the result, or `answer(saved store, result)`; StoreError
    saves nothing. `at`: the version the writer saw; if the store moved on since, the change is made on that version
    and Loro merges it with the rest (then `answer` gets the writer's own view)."""
    with store_lock():
        schema, d = load_schema(), document()
        if at and d is not None and d.version != at:
            return merged_write(d.doc, change, tidy, answer, at, schema)
        store, upgrading = load_store()
        new, result, *flags = change(store)
        new = finished(copy.deepcopy(new), tidy, schema, d.data if d is not None else None)
        save_data(new, upgrading, frozenset(flags[0]) if flags else frozenset())
        _written.version = current_version()
        return answer(new, result) if answer else result


def merged_write(doc, change, tidy, answer, at, schema):
    """transact's write on version `at` of `doc`, merged into it."""
    fork = fw_loro.fork_at(doc, at)
    seen = fw_loro.to_data(fork)
    new, result, *flags = change(prepared(seen))
    new = finished(copy.deepcopy(new), tidy, schema)
    new["schemaVersion"] = SCHEMA_VERSION
    stamp_updated(new, on_disk_read(seen), frozenset(flags[0]) if flags else frozenset(), now_local())
    write_doc(fork, new)
    try:
        fw_loro.merge_fork(doc, fork, at)
        write_doc(doc, finished(prepared(fw_loro.to_data(doc)), tidy, schema))  # (both sides' edits, checked again)
        save_doc(doc)
    except BaseException:
        forget()
        raise
    _written.version = fw_loro.version(fork)
    return answer(new, result) if answer else result


def editing(edit):
    """A change for transact from an edit in place, `edit(data, blocks)`, made on a copy of the store it's given."""
    def change(store: dict) -> tuple[dict, object, frozenset]:
        data = copy.deepcopy(store)
        result = edit(data, index(data))
        return data, result, frozenset(data.pop("rebased", ()))
    return change


def hashes(data: dict, *refs: str) -> dict:
    """The new content_hash of each of `refs`."""
    blocks = index(data)
    return {r: content_hash(blocks, r) for r in refs if r in blocks}


def restore(record: dict, tidy: bool = True) -> dict:
    """Blocks put back as `record` has them (None: removed; visits kept). Returns the record that puts back what was
    there instead (undo, then redo). With tidy off, nothing is erased yet."""
    def change(data, blocks):
        ids = {j for i in record["blocks"] if i in blocks for j in subtree(blocks, i)} | set(record["blocks"])
        inverse = {"blocks": {i: copy.deepcopy(blocks.get(i)) for i in ids}}
        for i, b in record["blocks"].items():
            data["blocks"] = [x for x in data["blocks"] if x.get("id") != i]
            if b is not None:
                data["blocks"].append(with_visits(copy.deepcopy(b), merge_visits(b.get("visits"), (blocks.get(i) or {}).get("visits"))))
        return inverse
    return transact(editing(change), tidy)


APPLIED_APART = {"kinds"}  # header fields applied on their own (set_kind), not with every save


def _apply_header(fw: dict, fields: list[dict], data: dict, schema: dict) -> list[str]:
    """The editable header `fields` copied into `fw`. Returns notes on edits refused."""
    props, editable, notes = schema.get("properties", {}), editable_keys(schema), []
    for field in fields:
        key = field.get("key")
        if key not in editable or not field.get("editable") or key in APPLIED_APART:
            continue
        if key == "title" and kind_of(fw) is not None:
            continue  # (a kind's title is its name: rename_kind)
        value = str(field.get("value", "")).strip()
        if value == "" and _type_ok(None, props[key].get("type", "string")):
            value = None
        if key == "title" and value and any(e.get("title") == value and e.get("id") != fw["id"] for e in data["blocks"]):
            notes.append(f"another pericope is already titled {value!r}; kept {fw.get('title')!r}")
            continue
        fw[key] = value
    return notes


def commit(entry_id: str, draft: str | None, fields: list[dict], final: bool = False,
           base: str | None = None, at: str | None = None) -> tuple[list[str], str, dict | None, dict]:
    """A block's draft text and header `fields` written (draft None: just the header). `final` discards an entry left
    empty and untitled; `base` (the content_hash it was built on) refuses a block changed elsewhere; `at` merges
    instead. Blocks the edit lets go of: their quotes keep what they showed (let_go). Returns (notes, its new
    content_hash, a record undoing what let_go changed or None, the quotes whose masks moved, as they were)."""
    def change(data, blocks):
        fw = blocks.get(entry_id)
        if fw is None:
            raise StoreError(f"no block with id {entry_id}")
        if draft is not None and base is not None and content_hash(blocks, entry_id) != base:
            raise StoreError("not saved: this block changed in another session since you opened it")
        notes, record, moved = _apply_header(fw, fields, data, load_schema()), None, {}
        if draft is not None:
            old, was_held = block_draft(blocks, entry_id), set(subtree(blocks, entry_id))
            write_content(data, blocks, fw, draft_items(draft, blocks, marked(blocks)))
            fw = blocks[entry_id]
            moved = rebase_quotes(data, entry_id, old, block_draft(blocks, entry_id), blocks=blocks)
            cut = {j for i in clip_holds() for j in subtree(blocks, i)}
            holders = held(blocks)
            record = let_go(data, blocks, {i for i in was_held if loose(blocks, i, holders) and i not in cut})
        if final and fw.get("entry") and is_empty_untitled(blocks, entry_id):
            fw.pop("entry")  # (erased when tidied)
            notes.append("nothing written, discarded empty pericope")
        return notes, record, moved
    return transact(editing(change), answer=lambda saved, r: (r[0], content_hash(index(saved), entry_id), r[1], r[2]), at=at)


def merge_file(path: str) -> str:
    """Another machine's .loro merged into this store, tidied, validated and saved (the same either way round)."""
    with store_lock():
        doc = fw_loro.load(LORO_PATH.read_bytes() if LORO_PATH.exists() else None, peer())
        if json_changed() and DATA_PATH.exists():  # the .json changed beside the document: its edits first
            write_doc(doc, load_data())
        was = {b["id"]: b for b in fw_loro.to_data(doc)["blocks"]}
        fw_loro.merge(doc, Path(path).read_bytes())
        data = fw_loro.to_data(doc)
        data = upgrade({**data, "blocks": masks_in(data["blocks"])}, now=now_local(), new_id=new_id)
        listed_once(data)
        tidy_store(data, clip_holds())
        sync_words(data)
        errs = invalid(data, load_schema())
        if errs:
            raise StoreError("the merged store is invalid, nothing saved: " + "; ".join(errs))
        write_doc(doc, data)
        after = {b["id"]: b for b in save_doc(doc).data["blocks"]}
        return (f"+{sum(i not in was for i in after)} new, ~{sum(i in was and after[i] != was[i] for i in after)} changed, "
                f"-{sum(i not in after for i in was)} removed blocks")
