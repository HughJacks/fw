"""fw_migrate — bringing an older store up to the current schema, in memory.

Pure: `upgrade(data, now=, new_id=)` takes the store as read from disk
(and the time and a maker of fresh ids, from the edge) and returns it at
SCHEMA_VERSION, as a new store, one small step per version (each changes
its own copy in place); `behind(data)` says whether it had to.
`fw_store.load_store` reads the file and calls both; `migrate` saves the
result. A store already current passes through untouched.
"""

from __future__ import annotations

import copy
from datetime import datetime

from fw.block import word_count
from fw.draft import trim_edges

SCHEMA_VERSION = 21


class BadStore(ValueError):
    """The store isn't one fw can read."""


def v2(data: dict, now: datetime, new_id) -> None:
    """`name` and the auto-derived `title` merged into one `title`, written
    by you or null (derived on display)."""
    for fw in data["freewrites"]:
        fw["title"] = fw.pop("name", None)


def v3(data: dict, now: datetime, new_id) -> None:
    """`content` became a list of child blocks; old text is one text block."""
    for fw in data["freewrites"]:
        if isinstance(fw.get("content"), str):
            fw["content"] = [{"type": "text", "text": fw["content"]}] if fw["content"] else []


def v4(data: dict, now: datetime, new_id) -> None:
    """Every block on its own, side by side. An entry is a block; each of its
    text blocks becomes a child block with an id of its own."""
    blocks, taken = [], {fw.get("id") for fw in data["freewrites"]}
    for fw in data["freewrites"]:
        try:
            created = datetime.fromisoformat(fw["created"])
        except (KeyError, TypeError, ValueError):
            created = now
        links, children = [], []
        for b in fw.get("content", []):
            if b.get("type") == "quote":
                links.append({"ref": b["ref"], "as": "quote"})
            elif trim_edges(b.get("text", "").split("\n")):
                text = "\n".join(trim_edges(b["text"].split("\n")))  # blank edges were only spacing
                cid = new_id(taken, created)
                taken.add(cid)
                children.append({"id": cid, "title": None, "content": text, "words": word_count(text),
                                 "created": created.isoformat(timespec="seconds")})
                links.append({"ref": cid})
        fw["content"] = links
        blocks += [fw, *children]
    data["entries"] = [fw.get("id") for fw in data.pop("freewrites")]
    data["blocks"] = blocks


def v5(data: dict, now: datetime, new_id) -> None:
    """No more links, only blocks. A container lists its children by id;
    each quote becomes a Quote block of its own in their place."""
    taken = {b.get("id") for b in data["blocks"]}
    for b in list(data["blocks"]):
        if isinstance(b.get("content"), list):
            kids = []
            for link in b["content"]:
                if link.get("as") == "quote":
                    qid = new_id(taken, datetime.fromisoformat(b["created"]) if b.get("created") else now)
                    taken.add(qid)
                    data["blocks"].append({"id": qid, "title": None, "content": {"quote": link["ref"]},
                                           "words": 0, "created": b.get("created")})
                    kids.append(qid)
                else:
                    kids.append(link["ref"])
            b["content"] = kids


def v7(data: dict, now: datetime, new_id) -> None:
    """Every block says when it last changed (`updated`); until now nothing
    was kept, so it starts as when it was made."""
    for b in data["blocks"]:
        b.setdefault("updated", b.get("created"))


def v10(data: dict, now: datetime, new_id) -> None:
    """Everything is a block. No `entries` list: an entry marks itself
    (`entry`: true), right after its title."""
    tops = set(data.pop("entries", []))
    data["blocks"] = [mark_entry(b) if b.get("id") in tops else b for b in data.get("blocks", [])]


def v18(data: dict, now: datetime, new_id) -> None:
    """A paraphrase is a block of its own, like a quote: the `paraphrases` mark on a block of text becomes its content,
    {paraphrase: the original, text: its words}. A mark on anything else (a
    block holding blocks, a picture; none were made) is dropped, the block as
    it was."""
    out = []
    for b in data.get("blocks", []):
        if "paraphrases" in b:
            b = {k: v for k, v in b.items() if k != "paraphrases"} | (
                {"content": {"paraphrase": b["paraphrases"], "text": b["content"]}} if isinstance(b.get("content"), str) else {})
        out.append(b)
    data["blocks"] = out


def v19(data: dict, now: datetime, new_id) -> None:
    """Only a pericope has kinds: a block inside one
    loses its answers, each yes carried up to its pericope unless the
    pericope answered about that kind itself (its own answer wins)."""
    blocks = {b.get("id"): b for b in data.get("blocks", [])}
    up = {}
    for b in data.get("blocks", []):
        c = b.get("content")
        for k in c if isinstance(c, list) else c.get("blocks", []) if isinstance(c, dict) and "kind" in c else []:
            up.setdefault(k, b.get("id"))
    def top(i, seen=()):
        return i if i not in up or i in seen else top(up[i], (*seen, i))
    for b in data.get("blocks", []):
        if b.get("entry") or not b.get("kinds"):
            continue
        t = blocks.get(top(b["id"]))
        if t is not None and t.get("entry"):
            for kid, yes in b["kinds"].items():
                if yes is True and kid != t.get("id"):
                    t.setdefault("kinds", {}).setdefault(kid, True)
        del b["kinds"]


def nothing(data: dict, now: datetime, new_id) -> None:
    """A new optional field nothing has yet, or a change only to how it's
    written: v6 (`show` on a quote), v8 (`inner`), v9 (`links`), v11 (masks
    written per block; in memory they stay anchors), v12 (an Image block), v13 (a link's `created`), v14 (`paraphrases`), v15 (`visits`:
    blocks from before have none), v16 (a Kind block, and `kinds` on any
    block: none yet), v17 (`lock` on a quote: none locked yet), v20 (an Expression block: none yet)."""


def v21(data: dict, now: datetime, new_id) -> None:
    """No Apply block (`{apply: [function, arguments…]}`): expressions live only in expression blocks. Any left
    becomes a plain container of the same blocks, so nothing written in one is lost."""
    for b in data.get("blocks", []):
        c = b.get("content")
        if isinstance(c, dict) and set(c) == {"apply"} and isinstance(c["apply"], list):
            b["content"] = list(c["apply"])


STEPS = [(2, v2), (3, v3), (4, v4), (5, v5), (6, nothing), (7, v7), (8, nothing),
         (9, nothing), (10, v10), (11, nothing), (12, nothing), (13, nothing), (14, nothing),
         (15, nothing), (16, nothing), (17, nothing), (18, v18), (19, v19), (20, nothing), (21, v21)]
assert STEPS[-1][0] == SCHEMA_VERSION


def mark_entry(b: dict) -> dict:
    """`b` marked as an entry (a top-level block), the mark after its title."""
    out = {}
    for k, v in b.items():
        if k != "entry":
            out[k] = v
        if k == "title":
            out["entry"] = True
    return out if "entry" in out else {**out, "entry": True}


def behind(data: dict) -> bool:
    """Store `data` is older than SCHEMA_VERSION: `upgrade` changes it, so it's to be saved (migrate)."""
    return data.get("schemaVersion", SCHEMA_VERSION) < SCHEMA_VERSION


def upgrade(data: dict, *, now: datetime, new_id) -> dict:
    """The store at SCHEMA_VERSION, each step it was behind applied in turn,
    as a new store (`data` as it was; whether it was behind: `behind`).
    `now` and `new_id(taken, created)` come from the edge (fw_store: the
    clock, fresh ids): a step that makes a block takes its time and id from
    them. Raises BadStore if it can't be read."""
    if not behind(data):  # (current: nothing to do, nothing copied)
        if not isinstance(data.get("blocks", []), list):
            raise BadStore("freewrites.json: `blocks` must be a list")
        return {**data, "schemaVersion": SCHEMA_VERSION, "blocks": data.get("blocks", [])}
    data = copy.deepcopy(data)  # (the steps change it where it stands: a copy of its own)
    data.setdefault("schemaVersion", SCHEMA_VERSION)
    if data["schemaVersion"] < 4:
        data.setdefault("freewrites", [])
        if not isinstance(data["freewrites"], list):
            raise BadStore("freewrites.json: `freewrites` must be a list")
    for version, step in STEPS:
        if data["schemaVersion"] < version:
            step(data, now, new_id)
            data["schemaVersion"] = version
    data.setdefault("blocks", [])
    if not isinstance(data["blocks"], list):
        raise BadStore("freewrites.json: `blocks` must be a list")
    return data
