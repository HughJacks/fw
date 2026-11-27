"""Visits: when blocks were looked at, written beside the edits (never an edit themselves)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fw.block import add_visits, index, masks_out, with_visits
from fw.store.disk import load_store, save_data
from fw.store.edit import put_block
from fw.store.paths import StoreError, store_lock
from fw.store.schema import load_schema, validate_instance


def clock() -> float:
    """Now, in seconds since the epoch; $FW_CLOCK names a file holding the time instead (tests)."""
    try:
        return float(Path(os.environ["FW_CLOCK"]).read_text())
    except (KeyError, OSError, ValueError):
        return time.time()


def record_visits(seen: dict) -> None:
    """Visits {block id: {minute: flags}} merged into the store: no `updated`, no undo, no tidying. Raises StoreError."""
    with store_lock():
        data, upgrading = load_store()
        blocks = index(data)
        hit = [i for i in seen if i in blocks and seen[i]]
        if not hit:
            return
        for i in hit:
            put_block(data, blocks, with_visits(blocks[i], add_visits(blocks[i].get("visits"), seen[i])))
        schema = load_schema()
        errs = [e for i in hit for e in validate_instance(masks_out([blocks[i]])[0], schema)]
        if errs:
            raise StoreError("visits not recorded, a block became invalid: " + "; ".join(errs))
        save_data(data, upgrading=upgrading)
