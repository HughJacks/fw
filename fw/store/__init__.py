"""fw's store: every block side by side in one Loro document (freewrites.loro), a .json copy beside it.

A block's shape is schema.json's: content is Text, Blocks (children by id), Quote (a live, maybe masked view of
another block), Image, Kind, Paraphrase or Expr. An entry (pericope) is a top-level block marked `"entry": true`;
a block no entry reaches is erased on the next write. Every write goes through `transact`.

    paths      where things live, the lock, StoreError
    schema     validating blocks against schema.json
    edit       edits in place: blocks added, put, their content written, quotes rebased
    tidy       what every write does to the whole store (tidying, words, `updated`)
    disk       the document on disk and in memory, its .json copy
    write      transact, commit, restore, merge_file
    quotes     masks, top lines, locks, detach, pop_out, nest_out, delete_entry
    text       hyperlinks and paraphrases
    kinds      tags, and a model's guesses and proposals
    pictures   image files and their titles
    visiting   visits and the clock
    clipboard  the rich clipboard
    cli        `python -m fw.store migrate | list | merge FILE`

What callers reach as `store.<name>` is re-exported here, the pure helpers with it. A name set on this package
(store.DATA_PATH = …, a test's stand-in for save_data) is set in every part that has it.
"""

import copy  # noqa: F401  (callers reach store.copy)
import sys
import types

from fw.draft import (  # noqa: F401
    QUOTE_RE, BLOCK_RE, IMAGE_RE, is_atom, atom_id, quote_line, image_line, block_line, chain, now_local,
    new_id, draft_place, parse_draft, parse_nest, format_draft, atom_draft, draft_items, draft_digest, expr_line, EXPR_RE,
)
from fw.lens import (  # noqa: F401
    ELLIPSIS, CLOSE, OPEN, MARKS, pieces, snap, normalize, empties, with_empties, holes, view, put, spans_of,
    intersect, minus, wrap, open_at, close_at, drop_anchor, tidy_edit, edit_mask, view_to_draft, draft_to_view,
    rebase,
)
from fw.block import (  # noqa: F401
    human_date, derive_title, word_count, index, children, kind_of, block_type, type_label, with_children,
    quoted, raw_mask, MAX_DEPTH, SHOWABLE, is_whole, image_of, expr_of, expr_refs, quote_show, quote_lock, locked_by, quote_inner,
    merge_inner, seen_quote, paraphrases, text_of, with_text, links, move_span, move_links, draft_leaves, carry_links, with_links,
    cut_links, pretty_time, own_text, block_items, items_text, full_text, shown_text, block_draft, child_lines,
    ancestors, content_hash, with_mask, home_of, regions, mask_to, backlinks, BACKLINK_NAMES, backlink_summary,
    families, per_block, flat_mask, masks_out, masks_in, with_inner, with_show, with_lock, quote_items, parents,
    held, loose, is_empty_untitled, display_title, pictures_held, picture_quote_id, entry_ids, sorted_entries,
    subtree, VISIT_GAP, VISIT_DWELL, visits, last_visit, minute_iso, add_visits, merge_visits, with_visits,
    attend, note_visits, ended, TOP, iso_minute, memory, last_action, garden, ago, GUESS_AT, MAYBE_AT, kinds_of,
    with_kinds, merge_kinds, guessed, learned, is_applied, maybes, kind_cover, open_proposals, kind_ids,
    tidy_name, same_name, kind_named, of_kind, parse_kinds, kinds_text,
)
from fw.migrate import SCHEMA_VERSION, BadStore, behind, upgrade  # noqa: F401
from fw.store import (
    paths, schema, edit, tidy, disk, clipboard, write, quotes, text, kinds, pictures, visiting, cli,
)
from fw.store.paths import (  # noqa: F401
    ROOT, DATA_PATH, LOCK_PATH, LORO_PATH, MIRROR_PATH, PEER_PATH, CLIP_PATH, IMAGES_PATH, TITLES_PATH, GUESSES_PATH,
    PROPOSALS_PATH, DISMISSED_PATH, SCHEMA_PATH, StoreError, store_lock, write_file, read_json_beside, die,
)
from fw.store.schema import load_schema, validate, validate_instance, apply_defaults, editable_keys, invalid  # noqa: F401
from fw.store.edit import (  # noqa: F401
    new_block, add_block, put_block, marked, set_content, write_content, set_container, quote_block, image_block,
    rebase_quotes, let_go,
)
from fw.store.tidy import (  # noqa: F401
    pictures_apart, kinds_apart, collect, tidy_store, sync_words, listed_once, stamp_updated,
)
from fw.store.disk import (  # noqa: F401
    Doc, peer, identity, json_changed, document, forget, on_disk, on_disk_read, prepared, load_store, load_data,
    current_version, load_versioned, json_text, write_json, json_later, flush_json, save_doc, store_text, save_data,
)
from fw.store.clipboard import save_clip, load_clip, clip_holds  # noqa: F401
from fw.store.write import (  # noqa: F401
    written_version, finished, transact, editing, hashes, restore, APPLIED_APART, commit, merge_file,
)
from fw.store.quotes import (  # noqa: F401
    quote_of, set_quote_mask, set_quote_masks, mask_quote_to, set_quote_show, set_quote_lock, detach, commit_view,
    pop_out, new_entry, nest_out, delete_entry,
)
from fw.store.text import (  # noqa: F401
    new_link, link_text, add_links, unlink_text, new_paraphrase, paraphrase_it, set_paraphrase,
)
from fw.store.kinds import (  # noqa: F401
    ONLY_PERICOPES, set_kinds, set_kind, new_kind, rename_kind, load_guesses, load_proposals, load_dismissed,
    dismiss_proposal, kind_from_proposal,
)
from fw.store.pictures import (  # noqa: F401
    MAX_DOWNLOAD, image_file, add_image, add_image_data, fetch_image, load_picture_titles, build_library,
)
from fw.store.visiting import clock, record_visits  # noqa: F401
from fw.store.cli import EMPTY_KEPT_MIN, cmd_migrate, cmd_list, main  # noqa: F401

PARTS = (paths, schema, edit, tidy, disk, clipboard, write, quotes, text, kinds, pictures, visiting, cli)


class Store(types.ModuleType):
    def __setattr__(self, name, value):
        """Set in every part that has `name` too, so they all see it."""
        for part in PARTS:
            if name in vars(part):
                setattr(part, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = Store
