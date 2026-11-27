"""The store on disk: a Loro document (kept in memory between reads) with a .json copy beside it."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from typing import NamedTuple

from fw import loro as fw_loro
from fw.block import masks_in, masks_out
from fw.draft import new_id, now_local
from fw.migrate import SCHEMA_VERSION, BadStore, behind, upgrade
from fw.store.paths import DATA_PATH, LORO_PATH, MIRROR_PATH, PEER_PATH, StoreError, store_lock, write_file
from fw.store.tidy import stamp_updated


def peer() -> int:
    """This machine's peer id in the document: made once, kept beside the store."""
    try:
        return int(PEER_PATH.read_text())
    except (OSError, ValueError):
        n = int.from_bytes(os.urandom(8), "big") >> 1
        PEER_PATH.write_text(str(n))
        return n


def identity(path, st=None) -> tuple | None:
    """Which version of a file this is (files are replaced whole: write_file)."""
    try:
        st = st or path.stat()
    except OSError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def digest(text: bytes) -> str:
    return hashlib.sha256(text).hexdigest()


def mirror() -> str:
    try:
        return MIRROR_PATH.read_text().strip()
    except OSError:
        return ""


_json_seen = [None, False]   # (the .json's and the mirror's identities, whether they differed) as last looked at


def json_changed() -> bool:
    """The .json was written by something else since the document last wrote it: it's taken in as edits."""
    key = (identity(DATA_PATH), identity(MIRROR_PATH))
    if key[0] is None:
        return False
    if _json_seen[0] != key:
        _json_seen[:] = [key, digest(DATA_PATH.read_bytes()) != mirror()]
    return _json_seen[1]


class Doc(NamedTuple):
    """The document as last read or written here: the file's identity, the Loro doc, what it says, its version."""
    key: tuple
    doc: object
    data: dict
    version: str


_doc: list = [None]   # the Doc in memory
_DOC = threading.RLock()


def kept(doc, key=None) -> Doc:
    """`doc` kept in memory as the file's (`key`, else the file's now)."""
    _doc[0] = Doc(key or identity(LORO_PATH), doc, fw_loro.to_data(doc), fw_loro.version(doc))
    return _doc[0]


def document() -> Doc | None:
    """The document, read again only when the file changed; None when there's none, or the .json changed beside it."""
    if json_changed():
        return None
    with _DOC:
        try:
            with open(LORO_PATH, "rb") as fh:
                key = identity(LORO_PATH, os.fstat(fh.fileno()))
                if _doc[0] is None or _doc[0].key != key:
                    kept(fw_loro.load(fh.read(), peer()), key)
        except FileNotFoundError:
            _doc[0] = None
        return _doc[0]


def forget() -> None:
    """The document in memory dropped (a write failed partway): read again next time."""
    with _DOC:
        _doc[0] = None


def on_disk() -> dict | None:
    """The store as on disk (masks per block, any schema): the document, or the .json changed beside it; None if none."""
    d = document()
    if d is not None:
        return copy.deepcopy(d.data)
    return json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else None


def on_disk_read(old: dict) -> list:
    """The blocks of the store as on disk, as they are in memory."""
    return masks_in(old["blocks"]) if old.get("schemaVersion", 0) >= 11 else old["blocks"]


def prepared(data: dict) -> dict:
    """The store as on disk, ready to use: masks as anchors, brought up to date."""
    if data.get("schemaVersion", SCHEMA_VERSION) >= 11 and isinstance(data.get("blocks"), list):
        data = {**data, "blocks": masks_in(data["blocks"])}
    try:
        return upgrade(data, now=now_local(), new_id=new_id)
    except BadStore as e:
        raise StoreError(str(e)) from e


def load_store() -> tuple[dict, bool]:
    """The store ready to use, and whether it was behind the schema (then saved with no `updated` stamped)."""
    data = on_disk()
    if data is None:
        return {"schemaVersion": SCHEMA_VERSION, "blocks": []}, False
    return prepared(data), behind(data)


def load_data() -> dict:
    return load_store()[0]


def current_version() -> str | None:
    """The store's version now (None: no document yet, or its .json changed beside it)."""
    d = document()
    return d.version if d is not None else None


def load_versioned() -> tuple[dict, str | None]:
    """The store as load_data reads it, and its version, from one reading."""
    d = document()
    return (load_data(), None) if d is None else (prepared(copy.deepcopy(d.data)), d.version)


def json_text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_json(data: dict) -> None:
    """The .json copy of `data` written, the old one kept as .bak, its mirror with it."""
    text = json_text(data).encode("utf-8")
    if DATA_PATH.exists():
        bak = DATA_PATH.with_suffix(".json.bak")
        bak.write_bytes(DATA_PATH.read_bytes())
        os.chmod(bak, 0o600)
    write_file(DATA_PATH, text)
    MIRROR_PATH.write_text(digest(text))


_later = {"after": None, "timer": None}


def json_later(seconds: float) -> None:
    """From now on in this process, the .json copy is written `seconds` after the last save, not with each one."""
    _later["after"] = seconds


def flush_json() -> None:
    """The .json copy brought up to the document, if it isn't; never over a .json someone else wrote meanwhile."""
    if _later["timer"]:
        _later["timer"].cancel()
    _later["timer"] = None
    with store_lock():
        d = document()
        if d is not None and (digest(json_text(d.data).encode("utf-8")) != mirror() or not DATA_PATH.exists()):
            write_json(d.data)


def save_doc(doc) -> Doc:
    """The document to disk and kept in memory (returned); its .json copy written now or later (json_later). Under the lock."""
    write_file(LORO_PATH, fw_loro.snapshot(doc))
    with _DOC:
        d = kept(doc)
    if _later["after"] is None:
        write_json(d.data)
        return d
    if _later["timer"]:
        _later["timer"].cancel()
    _later["timer"] = threading.Timer(_later["after"], flush_json)
    _later["timer"].daemon = True
    _later["timer"].start()
    return d


def store_text() -> str | None:
    """The store as its .json copy says it, as of now (even while that copy waits)."""
    d = document()
    if d is not None:
        return json_text(d.data)
    return DATA_PATH.read_text(encoding="utf-8") if DATA_PATH.exists() else None


def save_data(data: dict, upgrading: bool = False, rebased: frozenset = frozenset()) -> None:
    """The document edited to say `data` (just what changed) and saved; `updated` stamped on what changed, unless
    `upgrading`; `rebased`: quotes whose anchors only moved along."""
    data["schemaVersion"] = SCHEMA_VERSION
    d = document()
    old = d.data if d is not None else on_disk()
    stamp_updated(data, [] if upgrading or old is None else on_disk_read(old), rebased, now_local())
    doc = d.doc if d is not None else fw_loro.load(LORO_PATH.read_bytes() if LORO_PATH.exists() else None, peer())
    try:
        fw_loro.name_peer(doc, os.uname().nodename)
        fw_loro.write(doc, {**data, "blocks": masks_out(data["blocks"])}, d.data if d is not None else None)
        save_doc(doc)
    except BaseException:
        forget()
        raise


def write_doc(doc, data: dict) -> None:
    """Loro document `doc` made to say `data` (masks as anchors in memory, per block on disk)."""
    fw_loro.write(doc, {**data, "blocks": masks_out(data["blocks"])})
