#!/usr/bin/env python3
"""Storage backend for the `fw` free-writing command.

Everything is a block. All blocks live side by side in one JSON file
(freewrites.json), shaped as:

    {
      "schemaVersion": 16,
      "blocks":  [ <Block>, <Block>, ... ]
    }

The shape of one <Block> is defined by schema/block.schema.json, which is
the source of truth. A block's content is one of five shapes: Text, Blocks
(its children, by id), Quote (a live view of another block, maybe masked),
Image (one picture, a file in the `images` folder beside the store) or Kind
(what a block can be: a name and a description, its children).
An entry is a top-level block, marked `"entry": true`; a child has no mark
(its parent lists it). Deleting a block from its parent only unlinks it; a
block no entry reaches any more is erased on the next save. `migrate` is run on every `fw` invocation:
it backfills any newly-added schema properties (using their `default`) and
validates every entry, refusing to continue if an entry is broken in a way
it can't safely repair.

This module is the store's I/O, validation and writes. The pure parts it
builds on are their own modules, each using only the ones before it:
fw_draft (the draft text and ids), fw_lens (masks), fw_block (the block type).

Subcommands
    migrate            validate + backfill the whole store
    list               human-readable listing

The app (fw_app) stages an entry for editing with `stage` (a draft file and
its .meta.json sidecar, the header fields for the editor) and ends the
session with `finish`.
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

# the pure parts, in layers: the draft format, the lens (masks), the block
# type. Re-exported, so callers keep using store.<name> for all of them
from fw_draft import *  # noqa: F401,F403
from fw_lens import *  # noqa: F401,F403
from fw_block import *  # noqa: F401,F403
from fw_migrate import SCHEMA_VERSION, BadStore, upgrade
import fw_image
import fw_loro

HERE = Path(__file__).resolve().parent
DATA_PATH = Path(os.environ.get("FW_DATA") or HERE / "freewrites.json")  # FW_DATA: e.g. a test store
LOCK_PATH = DATA_PATH.with_name(".freewrites.lock")
LORO_PATH = DATA_PATH.with_suffix(".loro")  # the store itself: a Loro document (fw_loro); the .json beside it is a copy for reading
MIRROR_PATH = DATA_PATH.with_name(".freewrites.mirror")  # the hash of the .json as last written from the document
PEER_PATH = DATA_PATH.with_name(".freewrites.peer")  # this machine's peer id in the document (made once)
CLIP_PATH = DATA_PATH.with_name(".fw-clip.json")  # the rich clipboard (save_clip)
IMAGES_PATH = DATA_PATH.with_name("images")  # the pictures of Image blocks, named by what's in them (add_image)
THUMBS_PATH = DATA_PATH.with_name(".fw-thumbs")  # smaller copies of them to draw (picture_bytes); can go any time
GUESSES_PATH = DATA_PATH.with_name("kind-guesses.json")  # a model's guesses at kinds (written beside the store by a model outside fw)
MAX_DOWNLOAD = 50_000_000  # the biggest picture fetch_image takes
SCHEMA_PATH = HERE / "schema" / "block.schema.json"


# --------------------------------------------------------------------------- io

def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def peer() -> int:
    """This machine's peer id in the document: made once, kept beside the store."""
    try:
        return int(PEER_PATH.read_text())
    except (OSError, ValueError):
        n = int.from_bytes(os.urandom(8), "big") >> 1
        PEER_PATH.write_text(str(n))
        return n


def json_changed() -> bool:
    """The .json was written by something else since the document last wrote it
    (an older tool, a test): what it says is taken in as edits."""
    if not DATA_PATH.exists():
        return False
    try:
        mirror = MIRROR_PATH.read_text().strip()
    except OSError:
        mirror = ""
    return hashlib.sha256(DATA_PATH.read_bytes()).hexdigest() != mirror


def on_disk() -> dict | None:
    """The store as it is on disk (masks per block, any schema): the document,
    unless the .json has been changed beside it; None if there's none yet."""
    if LORO_PATH.exists() and not json_changed():
        return fw_loro.to_data(fw_loro.load(LORO_PATH.read_bytes(), peer()))
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return None


def load_data() -> dict:
    """The store, read and brought up to date in memory (fw_migrate), its
    masks as anchors for the lens (masks_in)."""
    data = on_disk()
    if data is None:
        return {"schemaVersion": SCHEMA_VERSION, "blocks": []}
    if data.get("schemaVersion", SCHEMA_VERSION) >= 11 and isinstance(data.get("blocks"), list):
        data["blocks"] = masks_in(data["blocks"])  # per block on disk, anchors for the lens
    try:
        return upgrade(data)
    except BadStore as e:
        die(str(e))


def write_file(path: Path, data: bytes) -> None:
    """`data` into `path` whole or not at all (a temp file, then a rename), private."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".freewrites.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_doc(doc) -> str:
    """The document to disk, and the .json copy of what it says; returns that copy."""
    write_file(LORO_PATH, fw_loro.snapshot(doc))
    text = json.dumps(fw_loro.to_data(doc), ensure_ascii=False, indent=2) + "\n"
    write_file(DATA_PATH, text.encode("utf-8"))
    MIRROR_PATH.write_text(hashlib.sha256(text.encode("utf-8")).hexdigest())
    return text


def save_data(data: dict) -> None:
    """The store written: the document edited to say `data` (fw_loro.write,
    the fewest edits), then saved with its .json copy (the old .json kept as .bak)."""
    upgrading = data.pop("upgraded", False)
    rebased = data.pop("rebased", set())
    data["schemaVersion"] = SCHEMA_VERSION
    old = on_disk()
    stamp_updated(data, [] if upgrading or old is None else on_disk_read(old), rebased)
    doc = fw_loro.load(LORO_PATH.read_bytes() if LORO_PATH.exists() else None, peer())
    fw_loro.name_peer(doc, os.uname().nodename)
    if DATA_PATH.exists():
        bak = DATA_PATH.with_suffix(".json.bak")
        bak.write_bytes(DATA_PATH.read_bytes())
        os.chmod(bak, 0o600)
    fw_loro.write(doc, {**data, "blocks": masks_out(data["blocks"])})
    save_doc(doc)


def merge_file(path: str) -> str:
    """Another machine's copy of the store (its .loro) merged into this one,
    then tidied as every write is (what no entry reaches erased, words
    recounted, a block listed twice kept once), validated, and saved. The same
    on both machines, in either order: they end up the same."""
    with store_lock():
        doc = fw_loro.load(LORO_PATH.read_bytes() if LORO_PATH.exists() else None, peer())
        if json_changed() and DATA_PATH.exists():  # the .json changed beside the document: its edits first
            mine = load_data()
            mine.pop("upgraded", None)
            mine.pop("rebased", None)
            fw_loro.write(doc, {**mine, "blocks": masks_out(mine["blocks"])})
        before = fw_loro.to_data(doc)
        fw_loro.merge(doc, Path(path).read_bytes())
        data = fw_loro.to_data(doc)
        data["blocks"] = masks_in(data["blocks"])
        data = upgrade(data)
        listed_once(data)
        collect(data, clip_holds())
        sync_words(data)
        errs = invalid(data, load_schema())
        if errs:
            raise StoreError("the merged store is invalid, nothing saved: " + "; ".join(errs))
        data.pop("upgraded", None)
        data.pop("rebased", None)
        fw_loro.write(doc, {**data, "blocks": masks_out(data["blocks"])})
        save_doc(doc)
        after = {b["id"]: b for b in fw_loro.to_data(doc)["blocks"]}
        was = {b["id"]: b for b in before["blocks"]}
        new = sum(i not in was for i in after)
        changed = sum(i in was and after[i] != was[i] for i in after)
        gone = sum(i not in after for i in was)
        return f"+{new} new, ~{changed} changed, -{gone} removed blocks"


def listed_once(data: dict) -> None:
    """After a merge, a block two containers list (moved on both machines) stays
    in the first of them by id, the same choice on every machine."""
    seen = set()
    for b in sorted(data["blocks"], key=lambda b: b["id"]):
        kids = children(b)
        if kids and any(k in seen for k in kids):
            with_children(b, [k for k in kids if k not in seen])
        seen.update(kids)


_guesses = (None, {})  # (the file's mtime and size, what it held) as last read
PROPOSALS_PATH = DATA_PATH.with_name("kind-proposals.json")  # the kinds a model proposes (written beside the store by a model outside fw)
DISMISSED_PATH = DATA_PATH.with_name("kind-dismissed.json")  # the proposals dismissed here: {dismissed: [{name, members, at}]}


def read_json_beside(path) -> dict:
    """A JSON object kept beside the store, as read; {} when there's none or it can't be read."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def load_proposals() -> dict:
    """kind-proposals.json beside the store, as read (fw_block.open_proposals keeps those still open)."""
    return read_json_beside(PROPOSALS_PATH)


def load_dismissed() -> dict:
    """kind-dismissed.json beside the store: the proposals dismissed."""
    return read_json_beside(DISMISSED_PATH)


def dismiss_proposal(p: dict) -> None:
    """Proposal `p` dismissed: kept in kind-dismissed.json (by name and
    members), so it isn't offered again. A fact of yours, kept beside
    the store rather than in it."""
    said = load_dismissed().get("dismissed")
    said = said if isinstance(said, list) else []
    entry = {"name": p.get("name"), "members": list(p.get("members") or []), "at": now_local().isoformat(timespec="seconds")}
    fd, tmp = tempfile.mkstemp(dir=DISMISSED_PATH.parent, prefix=".kind-dismissed.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"dismissed": said + [entry]}, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, DISMISSED_PATH)


def kind_from_proposal(p: dict) -> str:
    """A kind made from proposal `p` (fw_block.open_proposals'): a pericope
    named as proposed, its description a block of the drafted sentence and
    live quotes of the typical members still here. Refused when a kind
    has that name already. Returns the kind's id."""
    def change(data, blocks):
        name = tidy_name(p.get("name") or "")
        if not name:
            raise StoreError("a kind needs a name")
        if kind_named(blocks, name) is not None:
            raise StoreError(f"there's a kind called {name} already")
        parts = ([add_block(data, blocks, new_id(blocks), p["description"])["id"]] if p.get("description") else [])
        parts += [add_block(data, blocks, new_id(blocks), {"quote": t})["id"] for t in p.get("typical") or [] if t in blocks]
        return add_block(data, blocks, new_id(blocks), {"kind": name, "blocks": parts}, entry=True)["id"]
    return transact(change)


def load_guesses() -> dict:
    """kind-guesses.json beside the store, as read (fw_block.guessed keeps
    the guesses in it that count); {} when there's none or it can't be read.
    Read again only when the file changes, so it's cheap to ask often."""
    global _guesses
    try:
        st = GUESSES_PATH.stat()
    except OSError:
        return {}
    if _guesses[0] != (st.st_mtime_ns, st.st_size):
        try:
            got = json.loads(GUESSES_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            got = {}
        _guesses = ((st.st_mtime_ns, st.st_size), got if isinstance(got, dict) else {})
    return _guesses[1]


def on_disk_read(old: dict) -> list:
    """The blocks of the store as it was on disk, as they are in memory."""
    return masks_in(old["blocks"]) if old.get("schemaVersion", 0) >= 11 else old["blocks"]


def invalid(data: dict, schema: dict) -> list:
    """What's wrong with the blocks, as they'll be written (masks per block)."""
    return [f"block {b.get('id') or f'index {i}'}: {e}"
            for i, b in enumerate(masks_out(data["blocks"])) for e in validate_instance(b, schema)]


class StoreError(Exception):
    """A write the store refused; the message says why."""


@contextmanager
def store_lock():
    """Held around every read-modify-write of the store, so sessions saving at
    the same moment take turns instead of overwriting each other's entries."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)  # ($FW_DATA may name a folder not made yet)
    with open(LOCK_PATH, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def die(msg: str, code: int = 1):
    print(f"fw: {msg}", file=sys.stderr)
    sys.exit(code)


# ------------------------------------------------------------------- validation

def _type_ok(value, spec) -> bool:
    types = spec if isinstance(spec, list) else [spec]
    for t in types:
        if t == "string" and isinstance(value, str):
            return True
        if t == "null" and value is None:
            return True
        if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if t == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
    return False


def validate(value, spec: dict, where: str = "") -> list[str]:
    """A small draft-2020-12 checker for what block.schema.json uses: type,
    const, enum, pattern, minimum, `format: date-time`, oneOf, items,
    prefixItems, minItems, maxItems, and for
    objects required / properties / additionalProperties. Recursive, like
    the shapes it checks."""
    name = f"field `{where}`" if where else "entry"
    if "oneOf" in spec and not any(not validate(value, alt, where) for alt in spec["oneOf"]):
        return [f"{name} is none of the shapes it can be"]
    if "type" in spec and not _type_ok(value, spec["type"]):
        return [f"{name} has wrong type (want {spec['type']})"]
    errors = []
    if "const" in spec and value != spec["const"]:
        errors.append(f"{name} must be {spec['const']!r}")
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{name} must be one of {spec['enum']}")
    if isinstance(value, str):
        if spec.get("pattern") and not re.search(spec["pattern"], value):
            errors.append(f"{name} does not match {spec['pattern']}")
        if spec.get("format") == "date-time":
            try:
                datetime.fromisoformat(value)
            except ValueError:
                errors.append(f"{name} is not an ISO-8601 date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < spec.get("minimum", value):
        errors.append(f"{name} is below {spec['minimum']}")
    if isinstance(value, list):
        if not spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", len(value)):
            errors.append(f"{name} has {len(value)} items")
        first = spec.get("prefixItems", [])
        for n, item in enumerate(value):
            sub = first[n] if n < len(first) else spec.get("items")
            if sub is not None:
                errors += validate(item, sub, f"{where}[{n}]")
    if isinstance(value, dict):
        props = spec.get("properties", {})
        errors += [f"missing required field `{k}`" for k in spec.get("required", []) if k not in value]
        if spec.get("additionalProperties") is False:
            errors += [f"unexpected field `{k}`" for k in value if k not in props]
        elif isinstance(spec.get("additionalProperties"), dict):
            for k in value:
                if k not in props:
                    errors += validate(value[k], spec["additionalProperties"], f"{where}.{k}" if where else k)
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, f"{where}.{key}" if where else key)
    return errors


def validate_instance(obj, schema) -> list[str]:
    if not isinstance(obj, dict):
        return ["entry is not a JSON object"]
    return validate(obj, schema)


def apply_defaults(obj: dict, schema: dict) -> list[str]:
    """Add any schema property that is missing from `obj` and carries a
    `default`. Returns the names of the fields that were added."""
    added = []
    for key, spec in schema.get("properties", {}).items():
        if key not in obj and "default" in spec:
            obj[key] = spec["default"]
            added.append(key)
    return added


# --- writing content ---------------------------------------------------------

def rebase_quotes(data: dict, ref: str, old: str, new: str, skip: str | None = None) -> None:
    """Keep the mask of every quote of `ref` in step with an edit of it
    (noted in data["rebased"]: moving anchors along isn't an update)."""
    if old == new:
        return
    blocks = index(data)
    for b in data["blocks"]:
        q = quoted(b)
        if q and q[0] == ref and q[1] is not None and b.get("id") != skip:
            with_mask(b, normalize(new, rebase(old, new, q[1])))
            data.setdefault("rebased", set()).add(b.get("id"))
        inner = quote_inner(b)
        moved = {k: normalize(new, rebase(old, new, m)) for k, m in inner.items()
                 if (quoted(blocks.get(k)) or (None,))[0] == ref}
        if moved:
            with_inner(b, {**inner, **moved})
            data.setdefault("rebased", set()).add(b.get("id"))


def stamp_updated(data: dict, old_blocks: list, rebased: set = frozenset()) -> None:
    """`updated`, now, on every block whose title or content changed since
    `old_blocks` (the store as it was on disk), and on each block it's part
    of, up to its entry; not on blocks that quote it (their text lives in the
    source). Not a change: a quote's anchors moved along with an edit of its
    source (`rebased`), or the words recounted. An `updated` the write set
    itself stays (an undo putting a block back as it was)."""
    old = {b.get("id"): b for b in old_blocks}
    blocks = index(data)
    parents = {}
    for b in data["blocks"]:
        for k in children(b):
            parents.setdefault(k, []).append(b.get("id"))
    def kept(i):
        return old[i].get("updated") != blocks[i].get("updated")
    def changed(i):
        o, b = old[i], blocks[i]
        if i in rebased and quoted(o) and quoted(b) and quoted(o)[0] == quoted(b)[0]:
            return (quote_show(o), quote_lock(o)) != (quote_show(b), quote_lock(b))  # only the anchors moved, unless its line changed too
        return (o.get("title"), o.get("content")) != (b.get("title"), b.get("content"))
    now = now_local().isoformat(timespec="seconds")
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


def set_content(data: dict, blocks: dict, b: dict, items: list) -> None:
    """Make `items` (from draft_items) the content of block `b`. A block of
    plain text stays plain text while it holds one run of text; otherwise it
    becomes Blocks: each run of text a child block, updated in place or
    created when new, each quote a Quote block. Children it no longer lists
    are erased later, if nothing else reaches them."""
    if isinstance(b.get("content"), str) and all(i[0] == "text" for i in items) and len(items) <= 1:
        text = items[0][2] if items else ""
        with_links(b, move_links(b["content"], text, links(b)))
        b["content"] = text
        return
    mine = set(children(b))
    kids = []
    for item in items:
        if item[0] == "quote":
            kids.append(quote_block(data, blocks, b, item[1], item[2], kids))
            continue
        if item[0] == "image":
            kids += image_block(data, blocks, b, item[1], kids)
            continue
        if item[0] == "blocks":
            cid = item[1] if item[1] in mine or loose(blocks, item[1]) else None
            kids.append(set_container(data, blocks, cid, item[2], kids))
            continue
        _, bid, text = item
        if bid in blocks and bid not in mine and not loose(blocks, bid):
            bid = new_id(blocks)  # another block's id: this text is a copy, not that block
        if bid in blocks:  # (a container named as text: the editor folded its one block back into it)
            blocks[bid]["content"] = text
            blocks[bid]["content"] = text
        else:
            add_block(data, blocks, bid, text)
        kids.append(bid)
    with_children(b, kids)  # (a kind stays one: its description is these)


def new_block(bid: str, content, title=None, entry=False, links=()) -> dict:
    now = now_local().isoformat(timespec="seconds")
    block = {"id": bid, "title": title, **({"entry": True} if entry else {}),
             "content": content, "words": 0, "created": now, "updated": now}
    with_links(block, list(links))
    return block


def add_block(data: dict, blocks: dict, bid: str, content, title=None, entry=False) -> dict:
    block = new_block(bid, content, title, entry)
    data["blocks"].append(block)
    blocks[bid] = block
    return block


def write_content(data: dict, blocks: dict, b: dict, items: list) -> None:
    """set_content, the hyperlinks of the blocks in `b` carried along with
    the edit as one edit of its whole draft (carry_links): text that moves
    to another block, as when Enter splits one, keeps its links."""
    if isinstance(b.get("content"), str):
        set_content(data, blocks, b, items)
        return
    old = block_draft(blocks, b["id"])
    held = {i: links(blocks[i]) for i in subtree(blocks, b["id"]) if links(blocks.get(i))}
    set_content(data, blocks, b, items)
    if held:
        for bid, ls in carry_links(old, block_draft(blocks, b["id"]), held).items():
            if bid in blocks and isinstance(blocks[bid].get("content"), str):
                with_links(blocks[bid], ls)


def set_container(data: dict, blocks: dict, cid: str | None, items: list, kids: list) -> str:
    """The child block holding `items` (a container: a block of text with a
    quote nested in it): `cid`, or a new block. Left with one run of text
    and nothing else, it's a plain block of text again. Returns its id."""
    if cid is None:
        cid = add_block(data, blocks, new_id(set(blocks) | set(kids)), "")["id"]
    c = blocks[cid]
    if len(items) == 1 and items[0][0] == "text":
        c["content"] = items[0][2]
    else:
        if isinstance(c.get("content"), str):
            c["content"] = []  # (its text is in its children now, and its links with it: write_content)
            c.pop("links", None)
        set_content(data, blocks, c, items)
    return cid


def quote_block(data: dict, blocks: dict, b: dict, target: str, qid: str | None, kids: list) -> str:
    """The Quote block for a quote line in block `b`: its own (by id) stays,
    mask and all, and so does one no other block holds (back from an undo);
    one held elsewhere is copied, mask and all; a new quote is a new Quote
    block."""
    old = blocks.get(qid) if qid else None
    q = quoted(old)
    held_elsewhere = q is not None and any(qid in children(x) for x in blocks.values() if x is not b)
    if q and qid not in kids and (qid in children(b) or not held_elsewhere):
        if q[0] != target:
            old["content"] = {"quote": target}  # pointed somewhere else now: its mask no longer fits
        return qid
    nid = qid if qid and qid not in blocks else new_id(set(blocks) | set(kids))
    add_block(data, blocks, nid, copy.deepcopy(old["content"]) if q and q[0] == target else {"quote": target})
    return nid


def image_block(data: dict, blocks: dict, b: dict, iid: str, kids: list) -> list:
    """The Image block for an image line in block `b`, as a list of its id
    (none if there's no such block): its own stays, and so does a loose one
    (just put in); one held elsewhere is copied, the same picture."""
    name = image_of(blocks.get(iid))
    if name is None:
        return []
    if iid not in kids and (iid in children(b) or loose(blocks, iid)):
        return [iid]
    return [add_block(data, blocks, new_id(set(blocks) | set(kids)), {"image": name})["id"]]


def image_file(name: str) -> Path:
    return IMAGES_PATH / name


def add_image(src: str) -> str:
    """Copy picture file `src` into the images folder (add_image_data).
    Returns its name there; raises StoreError if it isn't a picture fw knows."""
    try:
        data = Path(src).expanduser().read_bytes()
    except OSError as e:
        raise StoreError(f"can't read {src}: {e.strerror}")
    return add_image_data(data, src)


def add_image_data(data: bytes, what: str) -> str:
    """Picture `data` (from `what`, for the error) into the images folder,
    named by a hash of its bytes (the same picture is kept once). Returns
    its name there; raises StoreError if it isn't a picture fw knows."""
    k = fw_image.kind(data[:16])
    if k is None:
        raise StoreError(f"not a png, jpeg, gif or webp: {what}")
    name = f"{hashlib.sha1(data).hexdigest()[:16]}.{k}"
    IMAGES_PATH.mkdir(exist_ok=True)
    if not image_file(name).exists():
        tmp = image_file(name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, image_file(name))
    return name


def fetch_image(url: str) -> bytes:
    """The bytes at web address `url` (for add_image_data: fw keeps its own
    copy, never the link). Raises StoreError."""
    import urllib.error, urllib.request  # (only here: it's slow to load)
    if not url.startswith(("http://", "https://")):
        raise StoreError("that's not a web address (http… or https…)")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) fw/1.0 (free-writing journal)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(MAX_DOWNLOAD + 1)
    except urllib.error.HTTPError as e:
        raise StoreError(f"couldn't download it: {e.code} {e.reason}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise StoreError(f"couldn't download it: {getattr(e, 'reason', e)}")
    if len(data) > MAX_DOWNLOAD:
        raise StoreError("that picture's too big (50 MB at most)")
    return data


def picture_bytes(name: str, width: int | None) -> bytes:
    """What to send the terminal to draw picture `name`: a jpeg copy
    `width` pixels wide (made once, with macOS's sips, and kept in
    .fw-thumbs), or the original (width None, or no copy could be made).
    Raises OSError if the picture's gone."""
    if width:
        thumb = THUMBS_PATH / f"{name.rsplit('.', 1)[0]}-{width}.jpg"
        if not thumb.exists():
            THUMBS_PATH.mkdir(exist_ok=True)
            tmp = thumb.with_suffix(".tmp.jpg")
            try:
                subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80",
                                "--resampleWidth", str(width), str(image_file(name)), "--out", str(tmp)],
                               capture_output=True, timeout=20, check=True)
                os.replace(tmp, thumb)
            except (OSError, subprocess.SubprocessError):
                pass  # (no sips: the original)
        if thumb.exists():
            return thumb.read_bytes()
    return image_file(name).read_bytes()


def collect(data: dict, keep=()) -> int:
    """Erase every block no entry reaches, through children or quotes (nor
    one of `keep`: blocks cut, that the clipboard holds, clip_holds).
    Returns how many were erased."""
    blocks, seen = index(data), set()
    todo = entry_ids(data) + list(keep)
    while todo:
        ref = todo.pop()
        if ref in seen or ref not in blocks:
            continue
        seen.add(ref)
        todo += children(blocks[ref])
        q = quoted(blocks[ref])
        if q:
            todo.append(q[0])
    kept = [b for b in data["blocks"] if b.get("id") in seen]
    gone = len(data["blocks"]) - len(kept)
    data["blocks"] = kept
    return gone


def sync_words(data: dict) -> bool:
    """Recount every block's words, quoted text included (derived, so kept
    quietly in step: a block grows when what it quotes grows)."""
    blocks, changed = index(data), False
    for b in data["blocks"]:
        words = word_count(full_text(blocks, b.get("id")))
        if b.get("words") != words:
            b["words"] = words
            changed = True
    return changed


def editable_keys(schema: dict) -> list[str]:
    """Fields a person edits in the editor header: everything not readOnly,
    except `content`, which is the editor body."""
    return [k for k, spec in schema.get("properties", {}).items()
            if not spec.get("readOnly") and k != "content"]


# -------------------------------------------------------------------- commands

def cmd_migrate(_args) -> None:
    schema = load_schema()
    data = load_data()
    changed = data.get("upgraded", False)
    if changed:
        print(f"fw: upgraded freewrites.json to schema v{SCHEMA_VERSION}", file=sys.stderr)
    before = json.dumps(data, sort_keys=True)
    fatal = []

    blocks = index(data)
    if len(blocks) != len(data["blocks"]):
        fatal.append("two blocks share an id")
    open_ids = _clean_drafts()
    for ref in entry_ids(data):
        if is_empty_untitled(blocks, ref) and ref not in open_ids:
            print(f"fw: removed empty untitled pericope {ref}", file=sys.stderr)
            blocks[ref].pop("entry")  # (erased by collect, below)

    for b in data["blocks"]:
        added = apply_defaults(b, schema)
        if added:
            print(f"fw: block {b.get('id')}: added field(s) {', '.join(added)}", file=sys.stderr)
    collect(data, clip_holds())
    sync_words(data)
    fatal += invalid(data, schema)

    if fatal:
        print("fw: freewrites.json failed validation:", file=sys.stderr)
        for f in fatal:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)

    if changed or json.dumps(data, sort_keys=True) != before or not DATA_PATH.exists() or not LORO_PATH.exists() or json_changed():
        save_data(data)  # (also the first time, making the document from the .json, and after the .json was changed beside it)


def find_entry(data: dict, title: str | None = None, last: bool = False) -> str | None:
    """The id of the newest entry with this written title (or a kind of this
    name, case aside), or of the newest entry."""
    entries = sorted_entries(data)
    if last:
        return entries[-1]["id"] if entries else None
    named = lambda fw: fw.get("title") == title or kind_of(fw) is not None and same_name(kind_of(fw), title)
    return next((fw["id"] for fw in reversed(entries) if title and named(fw)), None)


def meta_path(tmp: str) -> Path:
    return Path(tmp).with_suffix(".meta.json")


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _clean_drafts() -> set[str]:
    """Drafts of interrupted sessions stay next to the store for recovery;
    empty ones hold nothing, so drop them with their sidecars. Drafts whose
    fw session is still running are left alone. Returns the ids of entries
    open in a running session."""
    open_ids = set()
    for draft in HERE.glob(".fw-*.txt"):
        meta = meta_path(draft)
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {}
        if _alive(info.get("pid")):
            open_ids.add(info.get("id"))
        elif draft.stat().st_size == 0:
            draft.unlink()
            meta.unlink(missing_ok=True)
    for meta in HERE.glob(".fw-*.meta.json"):
        if not meta.with_name(meta.name.removesuffix(".meta.json") + ".txt").exists():
            meta.unlink()
    return open_ids


def _write_tmp(content: str, fw: dict, schema: dict, blocks: dict) -> str:
    """Stage a draft and its sidecar. The sidecar's `base` is the stored
    content the draft was built on, and `synced` the digest of the draft as
    last saved into the store (here: as written, since nothing is typed yet)."""
    # staged next to the store, so an interrupted session's draft stays here
    fd, tmp = tempfile.mkstemp(dir=HERE, prefix=".fw-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    editable = editable_keys(schema)
    shown = {"visits": lambda: minute_iso(last_visit(fw)), "kinds": lambda: kinds_text(blocks, fw)}  # (not as stored)
    fields = [{"key": k, "value": shown[k]() if k in shown else "" if fw.get(k) is None else str(fw[k]),
               "editable": k in editable} for k in schema.get("properties", {}) if k != "content"]
    for f in fields:
        if f["key"] == "title":  # shown when no title is written
            f["placeholder"] = kind_of(fw) or derive_title(own_text(blocks, fw["id"]))
    # pid: the fw session that owns this draft (fw_app runs as its child)
    meta_path(tmp).write_text(json.dumps({"id": fw["id"], "pid": os.getppid(), "fields": fields,
                                          "base": content_hash(blocks, fw["id"]), "synced": draft_digest(content)},
                                         indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return tmp


def stage(ref: str | None = None, title: str | None = None, append: bool = False) -> tuple[str, str, int]:
    """Stage an entry for editing, a new one (titled `title`) when `ref` is
    None: write its draft file and sidecar. Returns (id, draft path, the
    line to start on). Raises StoreError."""
    with store_lock():
        return _stage(ref, title, append)


def _stage(ref, title, append) -> tuple[str, str, int]:
    schema = load_schema()
    data = load_data()

    if ref is None:
        created = now_local()
        fw = {
            "id": new_id(index(data), created),
            "title": title or None,
            "entry": True,
            "content": [],
            "words": 0,
            "created": created.isoformat(timespec="seconds"),
            "updated": created.isoformat(timespec="seconds"),
        }
        errs = validate_instance(fw, schema)
        if errs:
            raise StoreError("cannot create pericope: " + "; ".join(errs))
        data["blocks"].append(fw)
        save_data(data)
        return fw["id"], _write_tmp("", fw, schema, index(data)), 1

    blocks = index(data)
    fw = blocks.get(ref)
    if fw is None:
        raise StoreError(f"no pericope with id {ref}")

    content = block_draft(blocks, fw["id"])
    if append and content:
        # open at the end: after its text (the editor puts the cursor there),
        # or below a quote, on a line of its own to write on (a new block,
        # trimmed again on save if nothing is written there)
        kids = children(fw)
        content += "\n" if kids and quoted(blocks.get(kids[-1])) else ""
    tmp = _write_tmp(content, fw, schema, blocks)
    return fw["id"], tmp, len(parse_draft(content)[0])  # the editor's line numbers leave out marker lines


APPLIED_APART = {"kinds"}  # header fields the editor applies itself (set_kind, from the kinds line), not on every save


def _apply_header(fw: dict, fields: list[dict], data: dict, schema: dict) -> list[str]:
    """Copy the editable header fields from the editor's sidecar into `fw`
    (but those APPLIED_APART). Returns notes about edits that were refused."""
    props = schema.get("properties", {})
    editable = editable_keys(schema)
    notes = []
    for field in fields:
        key = field.get("key")
        if key not in editable or not field.get("editable") or key in APPLIED_APART:
            continue  # only fields editable both now and when the session opened
        if key == "title" and kind_of(fw) is not None:
            continue  # (a kind's title field is its name: the editor renames it, rename_kind)
        value = str(field.get("value", "")).strip()
        if value == "" and _type_ok(None, props[key].get("type", "string")):
            value = None
        if key == "title" and value and any(
                e.get("title") == value and e.get("id") != fw["id"] for e in data["blocks"]):
            notes.append(f"another pericope is already titled {value!r}; kept {fw.get('title')!r}")
            continue
        fw[key] = value
    return notes


def commit(entry_id: str, draft: str | None, fields: list[dict], final: bool = False,
           base: str | None = None) -> tuple[list[str], str]:
    """Write one block's draft text and header fields into the store. The
    editor calls this on every autosave, so the store always holds the current
    text; `end` calls it with final=True, which also discards an entry left
    with no text and no title. Blocks no entry reaches any more are erased.
    With `base` (the content_hash the draft was built on), a block changed
    elsewhere since then is refused rather than overwritten. A draft of None
    leaves text and header as they are. A block the edit takes out (held by
    nothing now) goes as a deleted entry does: each quote of it elsewhere
    keeps the last of what it showed, as text (`let_go`). Returns (notes,
    the block's new content_hash, a record that puts back what that changed,
    or None); raises StoreError on refusal."""
    with store_lock():
        schema = load_schema()
        data = load_data()
        blocks = index(data)
        fw = blocks.get(entry_id)
        if fw is None:
            raise StoreError(f"no block with id {entry_id}")
        record = None
        if draft is None:
            notes = []
        elif base is not None and content_hash(blocks, entry_id) != base:
            raise StoreError("not saved: this block changed in another session since you opened it")
        else:
            notes = _apply_header(fw, fields, data, schema)
            old, was_held = block_draft(blocks, entry_id), set(subtree(blocks, entry_id))
            write_content(data, blocks, fw, draft_items(draft, blocks, marked(blocks)))
            rebase_quotes(data, entry_id, old, block_draft(blocks, entry_id))
            cut = {j for i in clip_holds() for j in subtree(blocks, i)}  # (cut, to be pasted: not gone)
            holders = held(blocks)
            record = let_go(data, blocks, {i for i in was_held if loose(blocks, i, holders) and i not in cut})
        if final and fw.get("entry") and is_empty_untitled(blocks, entry_id):
            fw.pop("entry")  # (erased by collect, below)
            notes.append("nothing written, discarded empty pericope")
        collect(data, clip_holds())
        sync_words(data)
        errs = invalid(data, schema)
        if errs:
            raise StoreError("refusing to save, a block became invalid: " + "; ".join(errs))
        save_data(data)
        return notes, content_hash(index(data), entry_id), record


def let_go(data: dict, blocks: dict, gone: set) -> dict | None:
    """Blocks `gone` (taken out, held by nothing): each quote of one of them
    (or of a block inside one) that stays keeps the last of what it showed,
    as text, and a link to it goes. Returns a record that puts them and those
    quotes back, or None when nothing quoted them."""
    gone = {j for i in gone for j in subtree(blocks, i)}
    quotes = [b for b in data["blocks"] if quoted(b) and quoted(b)[0] in gone and b.get("id") not in gone]
    if not quotes:
        return None
    undo = {"blocks": {i: copy.deepcopy(blocks[i]) for i in gone} | {q["id"]: copy.deepcopy(q) for q in quotes}}
    for q in quotes:
        q["content"] = shown_text(blocks, q["id"])
    return undo


def transact(change, tidy: bool = True):
    """One write to the store: under the lock, load, `change(data, blocks)`,
    tidy (erase what's unreachable, unless `tidy` is off), recount words,
    validate, save. Returns what `change` returns; raises StoreError (and
    saves nothing) on refusal."""
    with store_lock():
        schema = load_schema()
        data = load_data()
        result = change(data, index(data))
        if tidy:
            collect(data, clip_holds())
        sync_words(data)
        errs = invalid(data, schema)
        if errs:
            raise StoreError("refusing to save, a block became invalid: " + "; ".join(errs))
        save_data(data)
        return result


def hashes(data: dict, *refs: str) -> dict:
    """The new content_hash of each of `refs`, for an editor's bases."""
    blocks = index(data)
    return {r: content_hash(blocks, r) for r in refs if r in blocks}


def restore(record: dict, tidy: bool = True) -> dict:
    """Put blocks back as `record` has them, a
    block recorded as None removed (their visits aren't put back: they keep
    what they have, with the record's). Returns the record of what was there
    instead (with whatever now sits under those blocks), which puts it back
    in turn: undo, then redo. With tidy off, nothing is erased yet (a block
    coming back before what reaches it)."""
    def change(data, blocks):
        ids = {j for i in record["blocks"] if i in blocks for j in subtree(blocks, i)} | set(record["blocks"])
        inverse = {"blocks": {i: copy.deepcopy(blocks.get(i)) for i in ids}}
        for i, b in record["blocks"].items():
            data["blocks"] = [x for x in data["blocks"] if x.get("id") != i]
            if b is not None:
                b = copy.deepcopy(b)
                with_visits(b, merge_visits(b.get("visits"), (blocks.get(i) or {}).get("visits")))  # (not an edit: kept)
                data["blocks"].append(b)
        return inverse
    return transact(change, tidy)


def clock() -> float:
    """Now, in seconds since the epoch: what visits are timed by. $FW_CLOCK
    names a file holding the time instead (tests move it on, not sleep)."""
    try:
        return float(Path(os.environ["FW_CLOCK"]).read_text())
    except (KeyError, OSError, ValueError):
        return time.time()


def record_visits(seen: dict) -> None:
    """Write visits, {block id: {minute it began: flags}} (fw_block.attend),
    into the store, merged with what's there (another session's too: nothing
    is overwritten). Not an edit: no `updated`, no undo, nothing tidied, no
    words recounted; a block gone since is skipped. Raises StoreError."""
    with store_lock():
        schema = load_schema()
        data = load_data()
        blocks = index(data)
        hit = [i for i in seen if i in blocks and seen[i]]
        if not hit:
            return
        for i in hit:
            with_visits(blocks[i], add_visits(blocks[i].get("visits"), seen[i]))
        errs = [e for i in hit for e in validate_instance(masks_out([blocks[i]])[0], schema)]
        if errs:
            raise StoreError("visits not recorded, a block became invalid: " + "; ".join(errs))
        save_data(data)


def quote_of(blocks: dict, qid: str) -> tuple:
    q = quoted(blocks.get(qid))
    if q is None:
        raise StoreError(f"no quote {qid}")
    return q


def commit_view(qid: str, text: str, opened: int | None = None, base: str | None = None,
                seen: list | None = None) -> dict:
    """Save an edited view of masked quote `qid` into the block it shows
    (the lens's put), and move its mask along. `seen`: the mask it was seen
    with, when quotes around it narrow it (their inner masks); then the
    view goes back through that, and every mask moves along with the edit.
    Returns new content hashes of that block and of the blocks holding the
    quote."""
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
            rebase_quotes(data, target, old, stored)
        else:
            with_mask(blocks[qid], normalize(stored, rebase(draft, stored, new_mask)))
            rebase_quotes(data, target, old, stored, skip=qid)
        return target
    target = transact(change)
    data = load_data()
    return hashes(data, target, *parents(index(data), qid))


def set_quote_mask(qid: str, draft: str | None, mask: list | None, inner: bool = False) -> tuple[dict, dict]:
    """Mask quote `qid`: `mask` is anchors into `draft`, the text its target
    showed in the editor (moved onto the stored text). None shows all of it
    (with `inner`, its inner masks go too: all of it, as its source shows it).
    Returns (new content hashes of the blocks holding the quote, a record
    that undoes it with restore)."""
    def change(data, blocks):
        target, _ = quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        stored = block_draft(blocks, target)
        with_mask(blocks[qid], None if mask is None else normalize(stored, rebase(draft, stored, mask)))
        if inner:
            with_inner(blocks[qid], {})
        return undo
    undo = transact(change)
    data = load_data()
    return hashes(data, *parents(index(data), qid)), undo


def mask_quote_to(qid: str, block: str) -> tuple[dict, dict]:
    """Mask quote `qid` to show just `block` (somewhere in what it quotes)
    and all it holds. Returns (new content hashes of the blocks holding the
    quote, a record that undoes it with restore)."""
    def change(data, blocks):
        target, _ = quote_of(blocks, qid)
        if block not in subtree(blocks, target):
            raise StoreError("that block isn't in what it quotes")
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        draft = block_draft(blocks, target)
        with_mask(blocks[qid], normalize(draft, mask_to(blocks, target, draft, block)))
        return undo
    undo = transact(change)
    data = load_data()
    return hashes(data, *parents(index(data), qid)), undo


def delete_entry(eid: str) -> int:
    """Delete entry `eid`: it and every block it holds are erased. A quote is
    a pointer, so a quote of it elsewhere keeps the last of what it showed,
    as plain text (as Turn into text does). Returns how many quotes that was."""
    def change(data, blocks):
        if not blocks.get(eid, {}).get("entry"):
            raise StoreError(f"no pericope {eid}")
        gone = set(subtree(blocks, eid))
        kept = 0
        for b in data["blocks"]:
            q = quoted(b)
            if q and q[0] in gone and b.get("id") not in gone:
                b["content"] = shown_text(blocks, b["id"])
                kept += 1
            with_links(b, [link for link in links(b) if link["to"] not in gone])  # a link to it goes with it
            if b.get("paraphrases") in gone and b.get("id") not in gone:
                b.pop("paraphrases")  # (and a paraphrase of it is just your words)
            if any(k in gone for k in kinds_of(b)):
                with_kinds(b, {k: v for k, v in kinds_of(b).items() if k not in gone})  # (a kind gone: no answers about it)
        blocks[eid].pop("entry")  # (erased with what it holds once the change is tidied)
        return kept
    return transact(change)


def set_quote_masks(qid: str, own: tuple, inner: dict) -> tuple[dict, dict]:
    """Masking's result, in one write: quote `qid`'s own mask, `own` = (its
    target's text as masked, the mask: None shows all of it), and its inner
    masks, {quote id: (that quote's target's text, its mask, or None for
    none)}; each moved onto the stored text. Returns (new content hashes of
    the blocks holding `qid`, a record that undoes it)."""
    def change(data, blocks):
        target, _ = quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        stored = block_draft(blocks, target)
        text, mask = own
        with_mask(blocks[qid], None if mask is None else normalize(stored, rebase(text, stored, mask)))
        kept = dict(quote_inner(blocks[qid]))
        for iq, (draft, m) in inner.items():
            q = quoted(blocks.get(iq))
            if q is None or m is None:
                kept.pop(iq, None)
                continue
            st = block_draft(blocks, q[0])
            kept[iq] = normalize(st, rebase(draft, st, m))
        with_inner(blocks[qid], kept)
        return undo
    undo = transact(change)
    data = load_data()
    return hashes(data, *parents(index(data), qid)), undo


def set_quote_show(qid: str, show: list) -> tuple[dict, dict]:
    """Choose which of its target's properties quote `qid`'s top line shows.
    Returns (new content hashes of the blocks holding it, a record that undoes
    it with restore)."""
    def change(data, blocks):
        quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        with_show(blocks[qid], show)
        return undo
    undo = transact(change)
    data = load_data()
    return hashes(data, *parents(index(data), qid)), undo


def set_quote_lock(qid: str, on: bool) -> tuple[dict, dict]:
    """Lock quote `qid` (no writing through it; fw_block.locked_by), or
    unlock it. Returns (new content hashes of the blocks holding it, a record
    that undoes it with restore)."""
    def change(data, blocks):
        quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        with_lock(blocks[qid], on)
        return undo
    undo = transact(change)
    data = load_data()
    return hashes(data, *parents(index(data), qid)), undo


def detach(qid: str) -> tuple[str, dict, dict]:
    """Turn quote `qid` into text: a plain copy of what it shows, with no tie
    to where it came from. Returns (that text, new hashes of its holders, a
    record that undoes it with restore)."""
    def change(data, blocks):
        quote_of(blocks, qid)
        undo = {"blocks": {qid: copy.deepcopy(blocks[qid])}}
        text = shown_text(blocks, qid)
        blocks[qid]["content"] = text
        return text, undo
    text, undo = transact(change)
    data = load_data()
    return text, hashes(data, *parents(index(data), qid)), undo


def pop_out(ref: str) -> tuple[str, dict, dict]:
    """Turn block `ref` into a quote: what it holds (text, a picture, blocks:
    any content but a quote's) moves to a new block in a new entry of its
    own (titled from it), quoted where it was. Returns (the new entry's id,
    new hashes of the blocks holding it, a record that undoes it with
    restore: the new blocks gone, as if it never happened)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or quoted(b):
            raise StoreError("that's a quote already" if b else "that block is gone")
        if kind_of(b) is not None:
            raise StoreError("a kind is a pericope of its own already")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        moved = new_id(blocks)
        with_links(add_block(data, blocks, moved, copy.deepcopy(b["content"])), links(b))
        b.pop("links", None)
        if "paraphrases" in b:  # (a quote can't carry it: it goes with what it marks)
            blocks[moved]["paraphrases"] = b.pop("paraphrases")
        with_visits(blocks[moved], b.pop("visits", None))  # (likewise: they were visits to what it held)
        with_kinds(blocks[moved], kinds_of(b))  # (and what it is: it's what it holds that's a poem)
        b.pop("kinds", None)
        entry = add_block(data, blocks, new_id(blocks), [moved], entry=True)
        b["content"] = {"quote": entry["id"]}
        undo["blocks"].update({moved: None, entry["id"]: None})
        return entry["id"], undo
    entry, undo = transact(change)
    data = load_data()
    return entry, hashes(data, *parents(index(data), ref)), undo


def marked(blocks: dict) -> set:
    """The blocks marked as paraphrases (kept even while empty: draft_items)."""
    return {i for i, b in blocks.items() if b.get("paraphrases")}


def new_paraphrase(source: str, record: dict | None = None) -> tuple[str, dict]:
    """A new, empty block marked as a paraphrase of `source`, loose (the
    save that lists it takes it in). Returns (its id, a record that undoes
    it, merged into `record` if given: what was there before stays first)."""
    def change(data, blocks):
        if source not in blocks:
            raise StoreError("that block is gone")
        pid = new_id(blocks)
        add_block(data, blocks, pid, "")["paraphrases"] = source
        return pid
    pid = transact(change, tidy=False)
    undo = {"blocks": {pid: None, **((record or {}).get("blocks", {}))}}
    return pid, undo


def set_paraphrase(ref: str, source: str | None) -> dict:
    """Mark block `ref` as a paraphrase of block `source` (None: not one).
    Any block but a quote, of any block but itself. Returns a record that
    undoes it with restore."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError("that block isn't saved yet: write something first")
        if quoted(b):
            raise StoreError("a quote can't be a paraphrase (its content is a pointer already)")
        if source is not None and source not in blocks:
            raise StoreError("that block is gone")
        if source == ref:
            raise StoreError("a block can't paraphrase itself")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        if source is None:
            b.pop("paraphrases", None)
        else:
            b["paraphrases"] = source
        return undo
    return transact(change)


def _kind_called(data: dict, blocks: dict, name: str, undo: dict) -> str:
    """The kind called `name` (case and spacing aside), else a new one made
    with that name, as a pericope of its own (as "+ new pericope" makes one),
    noted in `undo` so taking it back takes the kind too."""
    kid = kind_named(blocks, name)
    if kid is None:
        if not tidy_name(name):
            raise StoreError("a kind needs a name")
        kid = add_block(data, blocks, new_id(blocks), {"kind": tidy_name(name), "blocks": []}, entry=True)["id"]
        undo["blocks"][kid] = None
    return kid


def set_kinds(ref: str, text: str) -> dict:
    """What block `ref` is, said as text (`text`, fw_block.parse_kinds: "poem,
    not letter"; as a script says it): each name an existing kind's (case aside),
    or a new kind (_kind_called); the answers it doesn't name go. Returns a
    record that undoes it with restore (the new kinds gone too)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError("that block isn't saved yet: write something first")
        undo, answers = {"blocks": {ref: copy.deepcopy(b)}}, {}
        for name, yes in parse_kinds(text):
            kid = _kind_called(data, blocks, name, undo)
            if kid == ref:
                raise StoreError(f"a kind can't be a kind of itself: {name}")
            answers[kid] = yes
        with_kinds(b, answers)
        return undo
    return transact(change)


def set_kind(ref: str, kind: str | None, answer: bool | None, name: str = "") -> tuple[str, dict]:
    """One answer about block `ref`: it is kind `kind` (True), it isn't
    (False), or no answer (None). With `kind` None, the kind called `name`,
    made if there's none (the kinds picker's "+ new kind"). Not an edit.
    Returns (the kind, a record that undoes it with restore, the kind made
    gone too)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError("that block isn't saved yet: write something first")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        kid = kind if kind is not None else _kind_called(data, blocks, name, undo)
        if kind_of(blocks.get(kid)) is None:
            raise StoreError("that kind is gone")
        if kid == ref:
            raise StoreError("a kind can't be a kind of itself")
        answers = kinds_of(b)
        if answer is None:
            answers.pop(kid, None)
        else:
            answers[kid] = answer  # (an answer changed keeps its place)
        with_kinds(b, answers)
        return kid, undo
    return transact(change)


def rename_kind(ref: str, name: str) -> dict:
    """Kind `ref` called `name` from now on (its spacing tidied): refused
    empty, or when another kind has that name (case aside). Whatever shows
    the name reads it from the kind, so it follows. Returns a record that
    undoes it with restore."""
    name = tidy_name(name)
    def change(data, blocks):
        b = blocks.get(ref)
        if kind_of(b) is None:
            raise StoreError("only a kind has a name to change")
        if not name:
            raise StoreError("a kind needs a name")
        other = kind_named(blocks, name)
        if other not in (None, ref):
            raise StoreError(f"there's a kind called {kind_of(blocks[other])} already")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        b["content"] = {**b["content"], "kind": name}
        b["title"] = None  # (its name is its title)
        return undo
    return transact(change)


def new_link(to: str, at: list) -> dict:
    """A hyperlink made now (a paste of one makes a new one: dated now too)."""
    return {"to": to, "at": at, "created": now_local().isoformat(timespec="seconds")}


def link_text(ref: str, text: str, span: list, to: str | None, title: str | None = None) -> tuple[str, dict]:
    """Make span `span` of text block `ref` (as offsets into `text`, its text
    as the editor has it) a hyperlink to entry `to`, or to a new entry titled
    `title` when `to` is None. Returns (the entry linked to, a record that
    undoes it with restore)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or not isinstance(b.get("content"), str):
            raise StoreError("only text can be linked")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        target = to
        if target is None:
            target = add_block(data, blocks, new_id(blocks), [], title or None, entry=True)["id"]
            undo["blocks"][target] = None
        elif not blocks.get(target, {}).get("entry"):
            raise StoreError("that pericope is gone")
        at = move_span(text, b["content"], span)  # (the stored text may differ at its edges)
        kept = [link for link in links(b) if not (link["at"][0] < at[1] and link["at"][1] > at[0])]
        with_links(b, sorted(kept + [new_link(target, at)], key=lambda link: link["at"]))
        return target, undo
    return transact(change)


def add_links(ref: str, text: str, new: list) -> dict:
    """Give text block `ref` the hyperlinks `new` ([{"to", "at"}], spans of
    `text`, its text as the editor has it; a link to an entry that's gone is
    left out), as a paste brings them. Returns a record that undoes it with restore."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or not isinstance(b.get("content"), str):
            raise StoreError("only text can be linked")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        added = [new_link(link["to"], move_span(text, b["content"], link["at"])) for link in new
                 if blocks.get(link["to"], {}).get("entry")]
        with_links(b, sorted(links(b) + added, key=lambda link: link["at"]))
        return undo
    return transact(change)


def save_clip(clip: dict | None) -> None:
    """Keep what was last copied in fw, for a paste in any session, even
    after fw quits: {"text": what went on the system clipboard, and "blocks"
    (whole blocks, as fw_blocks clips them; "cut": true when they were cut,
    so a paste moves them) or "links" (copied text's hyperlinks, as spans
    of it)}. None forgets it."""
    try:
        if clip is None:
            CLIP_PATH.unlink(missing_ok=True)
            return
        tmp = CLIP_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(clip, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, CLIP_PATH)
    except OSError:
        pass


def load_clip() -> dict | None:
    try:
        return json.loads(CLIP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clip_holds() -> list:
    """The blocks cut onto the clipboard: kept (not erased, their quotes kept
    live) until it holds something else, so a paste can move them."""
    clip = load_clip()
    return [u["id"] for u in clip.get("blocks", []) if u.get("id")] if clip and clip.get("cut") else []


def unlink_text(ref: str, to: str, at: list) -> dict:
    """Remove the hyperlink to `to` at `at` from text block `ref`. Returns a
    record that undoes it with restore."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None:
            raise StoreError(f"no block with id {ref}")
        undo = {"blocks": {ref: copy.deepcopy(b)}}
        with_links(b, [link for link in links(b) if not (link["to"] == to and link["at"] == at)])
        return undo
    return transact(change)


def nest_out(ref: str, before: str, middle: str, after: str) -> tuple[str, dict, dict]:
    """Turn part of text block `ref` (`middle`, between `before` and
    `after`) into a quote of a new entry holding it, nested where it was:
    `ref` becomes a container (its text before, the quote, its text after),
    or, if it's already in one, splits around the quote there. Returns (the
    new entry's id, new hashes of the blocks around it, a record that undoes
    it with restore)."""
    def change(data, blocks):
        b = blocks.get(ref)
        if b is None or not isinstance(b.get("content"), str):
            raise StoreError("only text can be turned into a quote")
        outer = next((p for p in parents(blocks, ref) if not blocks[p].get("entry")), None)
        top = ancestors(blocks, ref)  # (each of them drafts differently now)
        old = {t: block_draft(blocks, t) for t in top}
        undo = {"blocks": {i: copy.deepcopy(blocks[i]) for i in (ref, outer) if i}}
        for i, q in blocks.items():  # quotes of it elsewhere: their masks move along (rebase_quotes)
            if quoted(q) and quoted(q)[0] in top:
                undo["blocks"].setdefault(i, copy.deepcopy(q))
        text, ls = b["content"], links(b)
        at = text.find(middle, len(before))  # where the selection was (only space between it and `before`)
        pieces = {"before": (0, len(before)), "middle": (at, at + len(middle)), "after": (len(text) - len(after), len(text))}
        def new(content, piece=None, entry=False):
            block = add_block(data, blocks, new_id(blocks), content, entry=entry)
            if piece:
                with_links(block, cut_links(ls, *pieces[piece]))
            undo["blocks"][block["id"]] = None
            return block["id"]
        entry = new([new(middle, "middle")], entry=True)
        quote = new({"quote": entry})
        if outer is None:  # `ref` becomes the container
            b["content"] = ([new(before, "before")] if before else []) + [quote] + ([new(after, "after")] if after else [])
            b.pop("links", None)
        else:  # already in one: `ref` keeps the text before, if any
            b["content"] = before
            with_links(b, cut_links(ls, *pieces["before"]))
            kids = children(blocks[outer])
            i = kids.index(ref)
            kids[i:i + 1] = ([ref] if before else []) + [quote] + ([new(after, "after")] if after else [])
        for t in top:
            rebase_quotes(data, t, old[t], block_draft(blocks, t))
        return entry, top, undo
    entry, top, undo = transact(change)
    return entry, hashes(load_data(), *top), undo


def new_entry(title: str | None, host: str) -> tuple[str, dict]:
    """A new, empty entry (titled `title`), to be quoted in block `host`.
    Returns (its id, a record that undoes it with restore: the entry gone and
    `host` as it is now, so the quote of it goes too)."""
    def change(data, blocks):
        if host not in blocks:
            raise StoreError(f"no block with id {host}")
        undo = {"blocks": {host: copy.deepcopy(blocks[host])}}
        entry = add_block(data, blocks, new_id(blocks), [], title or None, entry=True)
        undo["blocks"][entry["id"]] = None
        return entry["id"], undo
    return transact(change)


def finish(ref: str, tmp: str) -> list[str]:
    """The last save of an editing session: its draft into the store (unless
    the editor already saved it), discarding an entry left empty. Returns
    notes; raises StoreError, in which case the draft is all there is."""
    draft = Path(tmp).read_text(encoding="utf-8")
    meta = meta_path(tmp)
    info = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
    # a draft the editor already saved is in the store (or newer text is, from
    # another session): only the empty-entry check is left to do
    synced = info.get("synced") == draft_digest(draft)
    notes, _, _ = commit(ref, None if synced else draft, info.get("fields", []), final=True, base=info.get("base"))
    return notes


def drop_draft(tmp: str) -> None:
    """Remove a staged draft and its sidecar, once the store has the writing."""
    for path in (Path(tmp), meta_path(tmp)):
        path.unlink(missing_ok=True)


def _row(fw: dict, blocks: dict) -> str:
    created = fw.get("created", "?")
    try:
        created = human_date(datetime.fromisoformat(created))
    except ValueError:
        pass
    label = display_title(blocks, fw["id"]) or "-"
    words = word_count(full_text(blocks, fw["id"]))
    return f"{fw.get('id','?'):<20}  {created:<21}  {label:<45}  {words:>5}w"


def cmd_list(args) -> None:
    data = load_data()
    entries = sorted_entries(data)
    if not entries:
        print("(no free writes yet)")
        return
    blocks = index(data)
    for fw in entries:
        print(_row(fw, blocks))


# ------------------------------------------------------------------------ main

def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="fw_store")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate")
    sub.add_parser("list")
    m = sub.add_parser("merge", help="merge another machine's freewrites.loro into this store")
    m.add_argument("file")

    args = p.parse_args(argv)
    if args.cmd == "merge":
        try:
            print(merge_file(args.file))
        except StoreError as e:
            die(str(e))
        return
    handler = {"migrate": cmd_migrate, "list": cmd_list}[args.cmd]
    if args.cmd == "migrate":  # it writes the store (the editor's writes lock themselves)
        with store_lock():
            handler(args)
    else:
        handler(args)


if __name__ == "__main__":
    main()
