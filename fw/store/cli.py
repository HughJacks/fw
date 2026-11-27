"""The store's commands: `python -m fw.store migrate | list | merge FILE`."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from fw.block import (
    display_title, entry_ids, full_text, human_date, index, is_empty_untitled, iso_minute, sorted_entries, word_count,
)
from fw.migrate import SCHEMA_VERSION
from fw.store.clipboard import clip_holds
from fw.store.disk import json_changed, load_data, load_store, save_data
from fw.store.paths import DATA_PATH, LORO_PATH, StoreError, die, store_lock
from fw.store.schema import apply_defaults, invalid, load_schema
from fw.store.tidy import sync_words, tidy_store
from fw.store.visiting import clock
from fw.store.write import merge_file

EMPTY_KEPT_MIN = 60  # an empty untitled pericope is cleared by migrate only once untouched this long


def cmd_migrate(_args) -> None:
    """The whole store validated and brought up to date: defaults filled, empty pericopes cleared, tidied, saved."""
    schema = load_schema()
    data, changed = load_store()
    if changed:
        print(f"fw: upgraded freewrites.json to schema v{SCHEMA_VERSION}", file=sys.stderr)
    before = json.dumps(data, sort_keys=True)
    blocks = index(data)
    fatal = ["two blocks share an id"] if len(blocks) != len(data["blocks"]) else []
    now = int(clock() // 60)
    for ref in entry_ids(data):
        touched = iso_minute(blocks[ref].get("updated"))
        if (touched is None or now - touched >= EMPTY_KEPT_MIN) and is_empty_untitled(blocks, ref):
            print(f"fw: removed empty untitled pericope {ref}", file=sys.stderr)
            blocks[ref].pop("entry")  # (erased when tidied)
    for b in data["blocks"]:
        added = apply_defaults(b, schema)
        if added:
            print(f"fw: block {b.get('id')}: added field(s) {', '.join(added)}", file=sys.stderr)
    tidy_store(data, clip_holds())
    sync_words(data)
    fatal += invalid(data, schema)
    if fatal:
        print("fw: freewrites.json failed validation:", file=sys.stderr)
        for f in fatal:
            print(f"  - {f}", file=sys.stderr)
        sys.exit(1)
    if changed or json.dumps(data, sort_keys=True) != before or not DATA_PATH.exists() or not LORO_PATH.exists() or json_changed():
        save_data(data, upgrading=changed)


def _row(fw: dict, blocks: dict) -> str:
    created = fw.get("created", "?")
    try:
        created = human_date(datetime.fromisoformat(created))
    except ValueError:
        pass
    words = word_count(full_text(blocks, fw["id"]))
    return f"{fw.get('id', '?'):<20}  {created:<21}  {display_title(blocks, fw['id']) or '-':<45}  {words:>5}w"


def cmd_list(_args) -> None:
    data = load_data()
    blocks = index(data)
    print("\n".join(_row(fw, blocks) for fw in sorted_entries(data)) or "(no free writes yet)")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="fw.store")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("list")
    sub.add_parser("merge", help="merge another machine's freewrites.loro into this store").add_argument("file")
    args = p.parse_args(argv)
    try:
        if args.cmd == "merge":
            print(merge_file(args.file))
        elif args.cmd == "migrate":
            with store_lock():
                cmd_migrate(args)
        else:
            cmd_list(args)
    except StoreError as e:
        die(str(e))
