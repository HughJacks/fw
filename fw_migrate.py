"""fw_migrate — bringing an older store up to the current schema, in memory.

Pure: `upgrade(data)` takes the store as read from disk and returns it at
SCHEMA_VERSION, one small step per version (each changes `data` in place,
which is freshly read and nobody else's). `fw_store.load_data` reads the
file and calls it; `migrate` saves the result. A store already current
passes through untouched.
"""

from __future__ import annotations

from datetime import datetime

from fw_block import word_count
from fw_draft import new_id, now_local, trim_edges

SCHEMA_VERSION = 17


class BadStore(ValueError):
    """The store isn't one fw can read."""


def v2(data: dict) -> None:
    """`name` and the auto-derived `title` merged into one `title`, written
    by you or null (derived on display)."""
    for fw in data["freewrites"]:
        fw["title"] = fw.pop("name", None)


def v3(data: dict) -> None:
    """`content` became a list of child blocks; old text is one text block."""
    for fw in data["freewrites"]:
        if isinstance(fw.get("content"), str):
            fw["content"] = [{"type": "text", "text": fw["content"]}] if fw["content"] else []


def v4(data: dict) -> None:
    """Every block on its own, side by side. An entry is a block; each of its
    text blocks becomes a child block with an id of its own."""
    blocks, taken = [], {fw.get("id") for fw in data["freewrites"]}
    for fw in data["freewrites"]:
        try:
            created = datetime.fromisoformat(fw["created"])
        except (KeyError, TypeError, ValueError):
            created = now_local()
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


def v5(data: dict) -> None:
    """No more links, only blocks. A container lists its children by id;
    each quote becomes a Quote block of its own in their place."""
    taken = {b.get("id") for b in data["blocks"]}
    for b in list(data["blocks"]):
        if isinstance(b.get("content"), list):
            kids = []
            for link in b["content"]:
                if link.get("as") == "quote":
                    qid = new_id(taken, datetime.fromisoformat(b["created"]) if b.get("created") else None)
                    taken.add(qid)
                    data["blocks"].append({"id": qid, "title": None, "content": {"quote": link["ref"]},
                                           "words": 0, "created": b.get("created")})
                    kids.append(qid)
                else:
                    kids.append(link["ref"])
            b["content"] = kids


def v7(data: dict) -> None:
    """Every block says when it last changed (`updated`); until now nothing
    was kept, so it starts as when it was made."""
    for b in data["blocks"]:
        b.setdefault("updated", b.get("created"))


def v10(data: dict) -> None:
    """Everything is a block. No `entries` list: an entry marks itself
    (`entry`: true), right after its title."""
    tops = set(data.pop("entries", []))
    data["blocks"] = [mark_entry(b) if b.get("id") in tops else b for b in data.get("blocks", [])]


def nothing(data: dict) -> None:
    """A new optional field nothing has yet, or a change only to how it's
    written: v6 (`show` on a quote), v8 (`inner`), v9 (`links`), v11 (masks
    written per block; in memory they stay anchors), v12 (an Image block), v13 (a link's `created`), v14 (`paraphrases`), v15 (`visits`:
    blocks from before have none), v16 (a Kind block, and `kinds` on any
    block: none yet), v17 (`lock` on a quote: none locked yet)."""


STEPS = [(2, v2), (3, v3), (4, v4), (5, v5), (6, nothing), (7, v7), (8, nothing),
         (9, nothing), (10, v10), (11, nothing), (12, nothing), (13, nothing), (14, nothing),
         (15, nothing), (16, nothing), (17, nothing)]
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


def upgrade(data: dict) -> dict:
    """The store at SCHEMA_VERSION, each step it was behind applied in turn
    (`upgraded` set, so it's saved). Raises BadStore if it can't be read."""
    data.setdefault("schemaVersion", SCHEMA_VERSION)
    if data["schemaVersion"] < 4:
        data.setdefault("freewrites", [])
        if not isinstance(data["freewrites"], list):
            raise BadStore("freewrites.json: `freewrites` must be a list")
    for version, step in STEPS:
        if data["schemaVersion"] < version:
            step(data)
            data["schemaVersion"] = version
            data["upgraded"] = True
    data.setdefault("blocks", [])
    if not isinstance(data["blocks"], list):
        raise BadStore("freewrites.json: `blocks` must be a list")
    return data
