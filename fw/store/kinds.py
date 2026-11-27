"""Kinds (tags): answers about pericopes, kinds made and renamed, and a model's guesses and proposals beside the store."""

from __future__ import annotations

import copy
import json
import os
import tempfile

from fw.block import kind_named, kind_of, kinds_of, parse_kinds, tidy_name, with_kinds
from fw.draft import new_id, now_local
from fw.store.edit import add_block, put_block
from fw.store.paths import DISMISSED_PATH, GUESSES_PATH, PROPOSALS_PATH, StoreError, cached_json, read_json_beside
from fw.store.write import editing, transact

ONLY_PERICOPES = "only a pericope has tags"


def _kind_called(data: dict, blocks: dict, name: str, undo: dict) -> str:
    """The kind called `name` (case and spacing aside), else a new pericope of that kind, noted in `undo`."""
    kid = kind_named(blocks, name)
    if kid is None:
        if not tidy_name(name):
            raise StoreError("a tag needs a name")
        kid = add_block(data, blocks, new_id(blocks), {"kind": tidy_name(name), "blocks": []}, entry=True)["id"]
        undo["blocks"][kid] = None
    return kid


def pericope(blocks: dict, ref: str) -> dict:
    """Block `ref`, refused unless it's a saved pericope (only those have kinds)."""
    b = blocks.get(ref)
    if b is None:
        raise StoreError("that block isn't saved yet: write something first")
    if not b.get("entry"):
        raise StoreError(ONLY_PERICOPES)
    return b


def set_kinds(ref: str, text: str) -> dict:
    """What pericope `ref` is, said as text ("poem, not letter"; kinds made as needed); answers not named go.
    Returns an undo record."""
    def change(data, blocks):
        b = pericope(blocks, ref)
        undo, answers = {"blocks": {ref: copy.deepcopy(b)}}, {}
        for name, yes in parse_kinds(text):
            kid = _kind_called(data, blocks, name, undo)
            if kid == ref:
                raise StoreError(f"a tag can't be a tag of itself: {name}")
            answers[kid] = yes
        put_block(data, blocks, with_kinds(b, answers))
        return undo
    return transact(editing(change))


def set_kind(ref: str, kind: str | None, answer: bool | None, name: str = "") -> tuple[str, dict]:
    """One answer about pericope `ref`: is kind `kind` (or the kind called `name`, made if none) True, False or
    None (no answer). Returns (the kind, an undo record)."""
    def change(data, blocks):
        b = pericope(blocks, ref)
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        kid = kind if kind is not None else _kind_called(data, blocks, name, undo)
        if kind_of(blocks.get(kid)) is None:
            raise StoreError("that tag is gone")
        if kid == ref:
            raise StoreError("a tag can't be a tag of itself")
        answers = kinds_of(b)
        if answer is None:
            answers.pop(kid, None)
        else:
            answers[kid] = answer
        put_block(data, blocks, with_kinds(b, answers))
        return kid, undo
    return transact(editing(change))


def new_kind(name: str) -> tuple[str, dict]:
    """The kind called `name`, made if there's none. Returns (it, an undo record)."""
    def change(data, blocks):
        undo = {"blocks": {}}
        return _kind_called(data, blocks, name, undo), undo
    return transact(editing(change))


def rename_kind(ref: str, name: str) -> dict:
    """Kind `ref` called `name` (tidied; refused empty or taken). Returns an undo record."""
    name = tidy_name(name)
    def change(data, blocks):
        b = blocks.get(ref)
        if kind_of(b) is None:
            raise StoreError("only a tag has a name to change")
        if not name:
            raise StoreError("a tag needs a name")
        other = kind_named(blocks, name)
        if other not in (None, ref):
            raise StoreError(f"there's a tag called {kind_of(blocks[other])} already")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        b["content"] = {**b["content"], "kind": name}
        b["title"] = None  # (its name is its title)
        return undo
    return transact(editing(change))


_guesses = [None, {}]


def load_guesses() -> dict:
    """kind-guesses.json beside the store (fw_block.guessed reads it); read again only when it changes."""
    return cached_json(GUESSES_PATH, _guesses, read_json_beside)


def load_proposals() -> dict:
    """kind-proposals.json beside the store (fw_block.open_proposals keeps those still open)."""
    return read_json_beside(PROPOSALS_PATH)


def load_dismissed() -> dict:
    """kind-dismissed.json beside the store: the proposals dismissed."""
    return read_json_beside(DISMISSED_PATH)


def dismiss_proposal(p: dict) -> None:
    """Proposal `p` kept in kind-dismissed.json (by name and members), so it isn't offered again."""
    said = load_dismissed().get("dismissed")
    entry = {"name": p.get("name"), "members": list(p.get("members") or []), "at": now_local().isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=DISMISSED_PATH.parent, prefix=".kind-dismissed.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"dismissed": (said if isinstance(said, list) else []) + [entry]}, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, DISMISSED_PATH)


def kind_from_proposal(p: dict) -> str:
    """A kind made from proposal `p`: named as proposed, described by its sentence and quotes of its typical members.
    Refused when the name's taken. Returns the kind's id."""
    def change(data, blocks):
        name = tidy_name(p.get("name") or "")
        if not name:
            raise StoreError("a tag needs a name")
        if kind_named(blocks, name) is not None:
            raise StoreError(f"there's a tag called {name} already")
        parts = [add_block(data, blocks, new_id(blocks), p["description"])["id"]] if p.get("description") else []
        parts += [add_block(data, blocks, new_id(blocks), {"quote": t})["id"] for t in p.get("typical") or [] if t in blocks]
        return add_block(data, blocks, new_id(blocks), {"kind": name, "blocks": parts}, entry=True)["id"]
    return transact(editing(change))
