#!/usr/bin/env python3
"""fw_edit — the plain-text editor fw opens entries in.

    fw_edit.py FILE [+LINE] [--meta META.json]

Soft word-wrapped editing with block numbers in the gutter, opened at LINE. Saves as
soon as you stop typing (there's no saving to do), and on quit. With --meta naming a stored entry,
each save also goes straight into the fw store, so the store always holds the
current text.

With --meta, a header above the text shows the entry's metadata: read-only
fields on one dim line, then one editable line per editable field (fw_store
writes the file from the schema and reads the edits back). Press Up on the
first line of text to move into the header; Down, Enter, Tab or Esc returns.

Keys: every key is in fw_keys.py (KEYS.md lists them, generated from it).

Blocks: an entry is a list of blocks, numbered in the gutter. Backspace at
the start of a block joins it to the one above. The editor asks the terminal
to report modified keys distinctly (the kitty keyboard protocol) and to mark
pastes (bracketed paste), so a pasted text stays one block. In FILE each block's text follows a
`{{block <id>}}` line, which the editor hides (only with --meta naming a
stored entry; otherwise FILE is plain text).

Every block is drawn in a box: a block of text in a dim one, a quote in a
red one, nested quotes as boxes inside it. Quotes: a line `{{quote <id>}}`
in FILE is drawn as that entry's current content inside its red box; the editor re-reads the store whenever it changes,
so edits made anywhere show up within about a second. Editing goes through:
what you type inside a quote is that entry's text, saved to it like your own
(and every copy on screen follows). Arrows stop on a quote, selected as a
unit, on the way in and on the way out: one more press in the same direction
goes inside (or on past it), the opposite one goes back; past the last quote
of the entry, a new empty line opens to write on. Clicking its text goes
straight in. Esc inside a quote, or Backspace on the line below it, also
selects it: then arrows move on, Backspace/Delete removes it, and Enter or
typing starts a new line below.
The status bar shows the title of the quote you're in or on, in red.
Quotes nest; a block already open further up (a cycle) is drawn as one "↻"
line, and nesting stops at MAX_DEPTH; those stand-ins can't be entered.

Standard library only (curses). If the terminal is closed mid-session, or the
editor crashes, unsaved text is also written to FILE before exiting.
"""

import copy
import curses
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import replace

import fw_image
import fw_keys as keys
import fw_store as store
from fw_blocks import BlockPicking
from fw_layout import THIN, Layout, box_edge, is_edge, link_ends, text_column
from fw_mask_ui import MaskEditing
from fw_menu import RUNS, Commands
from fw_screen import (SEEN, WHEEL_DOWN, Ink, cwidth, keyboard_modes, put, ready, setup, swidth,
                       word_left, word_right)
from fw_state import FieldEdit, Frame, View, Visits
from fw_store import (BLOCK_RE, IMAGE_RE, MAX_DEPTH, QUOTE_RE, atom_draft, atom_id, block_draft, block_line,  # same rules the store uses
                      chain, derive_title, format_draft, image_line, is_atom, parse_draft, parse_nest, quote_line)

UNDO_LIMIT = 500
WHEEL_ROWS = 3
AUTOSAVE_MS = 0     # idle time before saving: none, it saves as soon as the keys stop
POLL_MS = 250       # how often an idle editor checks the store for changes (what others saved)
RETRY_MS = 1000     # how soon a save the store refused is tried again
SETTLE_MS = 150     # pictures wait this long after the window last changed size before they're drawn
FETCH_MS = 100      # how often an editor waiting on a download checks it
# read-only header fields the editor recomputes as you type (same rule as fw_store)
LIVE = {"words": lambda ed: str(store.word_count(ed.entry_text())),
        "updated": lambda ed: ed.library.get(ed.self_id, {}).get("block", {}).get("updated")}
HIDDEN = {"id", "entry", "links"}  # header fields not worth showing (links are drawn in the text)
PRETTY = {"created": store.pretty_time, "updated": store.pretty_time, "visits": store.pretty_time}  # how a header field's value is shown
LABELS = {"visits": "last visited"}  # a header field shown under another name (visits: the last before this one)
HEADER_TOP = 2  # the header's first editable field's row: below its box's top and the line of read-only fields
# dim stand-ins for empty editable fields, recomputed as you type
PLACEHOLDERS = {"title": lambda lines: derive_title("\n".join(l for l in lines if not is_atom(l)))}
HELP = "⇧↵ line break  / menu  ^Q quit  ^Z undo "
# a masked quote's marks, as the editor holds them, and as they're drawn:
# a hidden stretch, and the two ends of the one laid open (anchors)
ELLIPSIS, CLOSE, OPEN = store.ELLIPSIS, store.CLOSE, store.OPEN
MARKS = store.MARKS


class Editor(Layout, MaskEditing, Commands, BlockPicking):
    def __init__(self, path: str, line: int, meta_path: str | None = None):
        self.path = path
        self.meta_path = meta_path
        self.meta = {"fields": []}
        if meta_path:
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    self.meta = json.load(fh)
            except (FileNotFoundError, json.JSONDecodeError):
                pass
        self.editable = [f for f in self.meta["fields"] if f.get("editable")]
        if self.meta.get("id") and self.meta["fields"]:  # (with a header to show it in; worked out from the store, not saved: fw_block.backlinks)
            self.editable.insert(0, {"key": "backlinks", "value": "", "derived": True})  # (above the title: Up reaches the title first)
        self.found = (None, [])
        self.peeking = set()  # the paraphrases whose source shows inside them (Show its source), this session  # (store mtime, backlinks of the open entry) as last worked out
        self.self_id = self.meta.get("id")  # the stored entry this session edits, if any
        # editing inside quotes: self.lines etc. are always the block being
        # edited (cur_id); the blocks it's quoted from wait on the stack
        self.cur_id = self.self_id
        self.stack = []         # [Frame], outermost first (fw_state: each mode and what it owns)
        self.history = {}       # id -> (undo, redo) of quoted blocks, kept between visits
        # id -> the stored content (store.content_hash) each open buffer was
        # built on: a save over content changed elsewhere since is refused
        self.base = {self.self_id: self.meta.get("base")} if self.self_id else {}
        # which side of the selected quote the cursor arrived on ("before" =
        # from above/left, "after" = from below/right, None = Esc/Backspace/
        # click): the next arrow away from that side goes inside
        self.unit_side = None
        self.library = {}       # id -> {title, words, blocks}, from the store
        self.store_mtime = None
        self.refresh_library()
        self.palette = None     # the / menu while open: a Menu
        self.ink = Ink()        # what it draws with (fw_screen.setup, once curses starts)
        self.can_draw_pictures = pictures_here()
        self.picture_px = {}    # each picture's size in pixels, by file name (read once)
        self.drawn = {}         # the pictures on screen: {(y, x, columns, rows, file name): what curses has in their cells}
        self.to_draw = {}       # those to draw once curses has drawn this frame (show_pictures), likewise
        self.escapes = {}       # each picture's escape, by (file name, columns, rows) (made once)
        self.screen_size = None  # the window's (rows, columns) last frame
        self.resized_at = 0.0   # when it last changed (pictures wait for it to settle)
        self.saved_meta = self.meta_values()
        self.fedit = None       # the header field being edited: a FieldEdit
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            text = ""
        text = text.replace("\r\n", "\n")
        # bids: for each line, the id of the block it's part of (None on a quote);
        # nest: each nested child's id -> the block it's in (a container)
        self.nest = {}
        if self.self_id:
            self.load_text(text, self.library)
        else:  # a plain file: one block, never saved as such
            self.lines = text.split("\n")
            self.bids = ["plain"] * len(self.lines)
        self.saved = self.snapshot()
        self.cy = min(max(line - 1, 0), len(self.lines) - 1)
        self.cx = 0
        self.goal_x = None      # screen column kept while moving up/down
        self.scroll = 0         # first screen row shown
        self.cols = None
        self.text_h = 1
        self.top = 0            # screen row where the text starts (below the header)
        self.stale = True       # layout needs rebuilding
        self.undo, self.redo = [], []
        self.last_edit = None   # kind of the current undo group
        self.message = ""
        self.prev_cr = False
        self.anchor = None      # (line, col) where the selection started
        self.picked = None      # blocks selected whole: a Picked (fw_blocks)
        self.joining = False    # next edit joins the current undo step
        self.clipboard = ""     # fallback when there's no system clipboard tool (clipboard_tool)
        self.pasting = False    # inside a bracketed paste: Enter there is a line break
        self.pasted = []        # the keys of a bracketed paste so far, (name, action) each, run when it ends
        self.vmode = None       # editing a masked quote's view: a View
        self.medit = None       # masking mode: a Masking
        self.confirming = None  # a question asked (y answers it): "delete"
        self.deleted = None     # the entry was deleted: how many quotes of it kept their text
        self.opening = None     # Open it: (the quote's target, where in its draft or None), for fw_app to step into
        self.made = None        # + new entry: (its id, undo depth), until coming back from it (came_back)
        self.trail = []         # titles of the entries stepped in from, outermost first (shown in the bar)
        self.refused = False    # the store refused the last save: retry it every RETRY_MS
        self.visits = Visits()  # the visits seen here, until they're written (fw_state)
        self.visit_open()

    @property
    def mode(self) -> str:
        """The mode the editor is in (fw_state): "menu", "header", "masking",
        "view", "quote" or "text"; keys go to its key_<mode>."""
        if self.palette is not None:
            return "menu"
        if self.fedit is not None:
            return "header"
        if self.medit is not None:
            return "masking"
        if self.vmode is not None:
            return "view"
        if self.picked is not None:
            return "blocks"
        return "quote" if self.stack else "text"

    # --- layout -------------------------------------------------------
    def is_atom(self, li: int) -> bool:
        """Line `li` is one block whole, selected as a unit: a quote, or an image."""
        return 0 <= li < len(self.lines) and is_atom(self.lines[li])

    def on_atom(self) -> bool:
        return self.is_atom(self.cy)

    def inner_at(self, level: int) -> dict:
        """The inner masks in force at stack level `level` (0: the entry):
        those of every quote open above it, each narrowing the next."""
        acc = {}
        for f in self.stack[:level]:
            q = self.quote_at(f.lines[f.anchor])
            if q and q[1] in self.library:
                acc = store.merge_inner(acc, store.quote_inner(self.library[q[1]]))
        return acc

    def seen_line(self, line: str, level: int) -> tuple:
        """Quote line `line`, at stack level `level`, as it's seen there:
        (target, its mask narrowed by the quotes open above it, show, the
        inner masks in force inside it)."""
        target, qid, mask = self.quote_at(line)
        acc = self.inner_at(level)
        if qid in self.library and store.quoted(self.library[qid]):
            return store.seen_quote(self.library, qid, acc)[1:]
        return target, mask, self.show_of(qid), acc

    def show_of(self, qid) -> list:
        """Which properties quote block `qid`'s top line shows."""
        return store.quote_show(self.library.get(qid, {}).get("block"))

    # --- quotes as editable blocks --------------------------------------
    def open_ids(self) -> list:
        """The entry, then each quote opened inside it, down to the one being edited."""
        return [f.id for f in self.stack] + [self.cur_id]

    def root_lines(self) -> list:
        return self.stack[0].lines if self.stack else self.lines

    def quote_at(self, line: str):
        """A quote line's (target, quote id, mask), else None."""
        m = QUOTE_RE.fullmatch(line)
        if not m:
            return None
        q = store.quoted(self.library.get(m.group(2))) if m.group(2) else None
        return m.group(1), m.group(2), q[1] if q else None

    def items_of(self, ref: str, mask=None, inner=None) -> list:
        """What a quote of `ref` (with `mask`) shows, as ("text", text) and
        ("quote", target, mask, show, inner) items, the quotes in it seen
        through `inner`: live from an editing buffer showing the same thing,
        so every copy on screen follows the typing, else as stored."""
        inner = inner or {}
        if ref == self.cur_id:
            lines, vmode = self.lines, self.vmode
        else:
            f = next((f for f in self.stack if f.id == ref), None)
            lines, vmode = (f.lines, f.vmode) if f else (None, None)
        if lines is None or (mask is None) != (vmode is None):
            return store.quote_items(self.library, ref, mask, inner=inner)
        out = []
        for line in lines:
            q = self.quote_at(line)
            if q and q[1] in self.library and store.quoted(self.library[q[1]]):
                out.append(store.seen_quote(self.library, q[1], inner))
            elif image := IMAGE_RE.fullmatch(line):
                out.append(("image", image.group(1)))
            else:
                out.append(("quote", q[0], q[2], [], inner) if q else ("text", line))
        return out

    def entry_text(self) -> str:
        """The entry's text as typed so far, quoted text flattened in (the store's rule)."""
        return store.items_text(self.library, self.items_of(self.self_id), {self.self_id})

    def enterable(self, li: int) -> bool:
        """The quote on line `li` can be gone into: it's drawn in its box (not
        a stand-in for one too deep, a loop, or a missing block)."""
        m = QUOTE_RE.fullmatch(self.lines[li]) if 0 <= li < len(self.lines) else None
        if m is None or m.group(1) not in self.library or m.group(1) in self.open_ids():
            return False
        if store.is_whole(self.library[m.group(1)]["block"]):
            return False  # (nothing in it to write in: a picture)
        self.ensure_layout()
        top = self.rows[self.first_row[li]].drawn
        return top is not None and top.kind == "top"

    def enter(self, li: int, at_end: bool = False) -> None:
        """Start editing the quote on line `li`: its block becomes self.lines."""
        if self.medit:
            self.mask_into(li, at_end)  # masking: its mask, seen through the one being made
            return
        if self.dirty():
            self.save()
        _, qid, _ = self.quote_at(self.lines[li])
        ref, mask, _, _ = self.seen_line(self.lines[li], len(self.stack))  # narrowed by the quotes around it
        self.stack.append(Frame(self.cur_id, self.lines, self.bids, self.saved, li, self.undo, self.redo, self.vmode,
                                self.nest))
        self.cur_id, self.vmode = ref, None
        if mask is not None:
            self.load_view(qid, mask, None)  # a masked quote: edit what it shows
        else:
            self.load_text(block_draft(self.library, ref))
            self.saved = self.snapshot()
        self.base[ref] = store.content_hash(self.library, ref)
        self.undo, self.redo = self.history.get((ref, self.vmode and qid), ([], []))
        self.cy, self.cx = (len(self.lines) - 1, len(self.lines[-1])) if at_end else (0, 0)
        self.anchor = None
        self.last_edit = None
        self.stale = True

    def leave(self) -> None:
        """Stop editing the current quote (saving it); the cursor lands on it, as a unit."""
        if self.medit and len(self.medit.keys) > 1:
            self.mask_out()  # out of a quote inside the one being masked: still masking
            return
        if self.medit:
            self.exit_mask()
        if self.dirty():
            self.save()
        self.history[(self.cur_id, self.vmode and self.vmode.qid)] = (self.undo, self.redo)
        f = self.stack.pop()
        self.cur_id, self.lines, self.bids, self.saved = f.id, f.lines, f.bids, f.saved
        self.vmode, self.nest = f.vmode, f.nest
        self.undo, self.redo = f.undo, f.redo
        self.cy, self.cx = f.anchor, 0
        self.anchor = None
        self.last_edit = None
        self.stale = True
        self.refresh_library()
        self.follow_store()

    def load_view(self, qid: str, mask: list, opened, clear: bool = True) -> None:
        """Make the buffer the view of masked quote `qid` (of cur_id), with
        hidden stretch `opened` laid open (None: all shut)."""
        text = store.view(block_draft(self.library, self.cur_id), mask, opened)
        self.load_text(text)
        marked = {m.group(1) for m in BLOCK_RE.finditer(text)}
        # text whose block marker is out of sight (hidden) is part of that block: no marker of its own
        self.vmode = View(qid, opened, {b for b in self.bids if b and b not in marked})
        self.saved = self.snapshot()
        if clear:
            self.undo, self.redo = [], []  # the view's shape changed: old steps no longer fit
        self.stale = True

    def view_mask(self):
        """The mask the quote whose view is being edited is seen with: its own,
        narrowed by the inner masks of the quotes around it."""
        if not self.vmode or not self.stack:
            return None
        f = self.stack[-1]
        return self.seen_line(f.lines[f.anchor], len(self.stack) - 1)[1]

    def arrive(self) -> None:
        """Just entered a masked view: start past a leading …, or before a trailing one."""
        if not self.vmode:
            return
        line = self.lines[self.cy]
        if self.cx == 0 and line[:1] == ELLIPSIS and self.cy == 0:
            self.cx = 1
        elif self.cx == len(line) and line[-1:] == ELLIPSIS and self.cy == len(self.lines) - 1:
            self.cx -= 1

    # --- movement -----------------------------------------------------
    def left(self) -> None:
        if self.on_atom():
            if self.anchor is None and self.unit_side == "after" and self.enterable(self.cy):
                self.enter(self.cy, at_end=True)
                self.arrive()
                return
        elif self.cx > 0:
            self.cx -= 1
            return
        if self.cy > 0:
            self.cy -= 1
            self.cx = len(self.lines[self.cy])
            self.unit_side = "after"  # if that's a quote, it's now selected
        elif self.stack and self.anchor is None:
            self.leave()  # out through the start of a quote: it's selected
            self.unit_side = "before"

    def right(self) -> None:
        if self.on_atom():
            if self.anchor is None and self.unit_side == "before" and self.enterable(self.cy):
                self.enter(self.cy)
                self.arrive()
                return
        elif self.cx < len(self.lines[self.cy]):
            self.cx += 1
            return
        if self.cy < len(self.lines) - 1:
            self.cy += 1
            self.cx = 0
            self.unit_side = "before"  # if that's a quote, it's now selected
        elif self.stack and self.anchor is None:
            self.leave()  # out through the end of a quote: it's selected
            self.unit_side = "after"
        elif self.on_atom() and self.anchor is None:
            self.open_after_quote()  # past the entry's last quote: a line to write on

    def word_left(self) -> None:
        if self.cx == 0:
            self.left()
        else:
            self.cx = word_left(self.lines[self.cy], self.cx)

    def word_right(self) -> None:
        if self.cx == len(self.lines[self.cy]) or self.on_atom():
            self.right()
        else:
            self.cx = word_right(self.lines[self.cy], self.cx)

    def home(self) -> None:
        self.cx = 0

    def end(self) -> None:
        self.cx = len(self.lines[self.cy])

    def move_vert(self, delta: int) -> None:
        self.ensure_layout()
        r = self.cursor_row()
        li, start, _, q, _ = self.rows[r]
        if self.goal_x is None:
            self.goal_x = 0 if q else self.col_x(li, start, self.cx)
        forward = delta > 0
        if q is not None:  # on a quote selected as a unit
            if (self.anchor is None and self.enterable(li)
                    and self.unit_side == ("before" if forward else "after")):
                self.enter(li, at_end=not forward)  # carry on into it
                self.ensure_layout()
                self.goto_row(self.first_row[0] if forward else self.active_end, self.goal_x, forward)
                self.arrive()
                return
            r = self.last_row(li) if forward else self.first_row[li]  # step past it
            if not 0 <= r + (1 if forward else -1) < len(self.rows):  # nothing beyond it
                if self.stack:
                    self.leave()
                    self.unit_side = "after" if forward else "before"
                elif forward:
                    self.open_after_quote()  # past the entry's last quote: a line to write on
                else:
                    self.unit_side = "before"
                return
        self.goto_row(r + delta, self.goal_x, forward)

    def goto_row(self, t: int, want_x: int, forward: bool = True, click: bool = False) -> None:
        """Put the cursor on layout row `t`, as near `want_x` columns into its
        text as it goes. Moving onto a quote, or out of the one being edited,
        selects that quote as a unit; a click goes straight to the text, in or
        out of quotes. While selecting, the cursor stays in the block where
        the selection started."""
        if not click and self.stack and self.anchor is None and not 0 <= t < len(self.rows):
            self.leave()  # out past the top or bottom of the screen's text
            self.unit_side = "after" if t >= len(self.rows) else "before"
            return
        t = min(max(t, 0), len(self.rows) - 1)
        if self.is_gap(t):  # a text block's top or bottom: on into the text
            t = self.past_gaps(t, (1 if self.rows[t].drawn.kind == "top" else -1) if click else (1 if forward else -1))
        if click:
            for _ in range(2 * MAX_DEPTH + 2):
                li, q = self.rows[t].line, self.rows[t].drawn
                if li is None:
                    self.leave()
                elif q is not None and not is_edge(q) and self.enterable(li):
                    self.enter(li)  # a click on a quote's box selects it; on its text, goes in
                else:
                    break
                self.ensure_layout()
        elif self.rows[t].line is None:  # outside the block being edited
            if self.anchor is not None:
                t = self.first_row[0] if t < self.first_row[0] else self.active_end
            else:
                self.leave()
                self.unit_side = "after" if forward else "before"
                return
        li, start, end, q, _ = self.rows[t]
        if q is not None:
            self.cy, self.cx = li, 0
            self.unit_side = None if click else ("before" if forward else "after")
            return
        self.cy, self.cx = li, self.col_at(t, want_x)

    def col_at(self, t: int, want_x: int) -> int:
        """The column of row `t`'s line nearest `want_x` screen columns into the row."""
        li, start, end, _, _ = self.rows[t]
        last = t + 1 >= len(self.rows) or self.rows[t + 1].line != li
        limit = end if last else max(end - 1, start)  # `end` belongs to the next row
        line, x, col = self.lines[li], 0, start
        ends = link_ends(self.spans_now[li])
        while col < limit and x + cwidth(line[col]) <= want_x:
            x += cwidth(line[col]) + (col + 1 in ends)  # (a link's ↗ after it)
            col += 1
        return col

    # --- editing ------------------------------------------------------
    def checkpoint(self, kind: str, force: bool = False) -> None:
        """Snapshot for undo when a new group of edits starts."""
        if self.joining:
            self.joining = False
        elif force or kind != self.last_edit:
            self.push_undo()
        self.last_edit = kind
        self.stale = True

    def insert(self, ch: str) -> None:
        self.checkpoint("type", force=ch == " ")  # undo a word at a time
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx] + ch + line[self.cx:]
        self.cx += 1

    def line_break(self) -> None:
        """Shift+Enter: a new line in the same block."""
        self.checkpoint("newline", force=True)
        line = self.lines[self.cy]
        self.lines[self.cy:self.cy + 1] = [line[:self.cx], line[self.cx:]]
        self.bids.insert(self.cy + 1, self.bids[self.cy])
        self.cy += 1
        self.cx = 0

    def newline(self) -> None:
        """Enter: a new block from the cursor on, taking the rest of this
        block with it. At the very start of a block the new, empty one goes
        above instead, so the text keeps its block."""
        if not self.self_id or self.pasting:
            return self.line_break()  # a plain file has no blocks; a paste stays one
        if self.step_out():
            return
        bid = self.bids[self.cy]
        top, last = self.block_at(self.cy) if bid else (0, -1)
        if store.paraphrases(self.library.get(bid)):
            if any(l.strip() for l in self.lines[top:last + 1]):
                self.nest_in()  # a paraphrase grows: a block inside it, not after it
                return
            self.checkpoint("newline", force=True)  # not written yet: a block after it, not above
            self.lines.insert(last + 1, "")
            self.bids.insert(last + 1, self.fresh(self.nest.get(bid)))
            self.cy, self.cx = last + 1, 0
            return
        self.checkpoint("newline", force=True)
        line, bid = self.lines[self.cy], self.bids[self.cy]
        at_start = self.cx == 0 and (self.cy == 0 or self.bids[self.cy - 1] != bid)
        self.lines[self.cy:self.cy + 1] = [line[:self.cx], line[self.cx:]]
        self.bids.insert(self.cy + 1, bid)
        new = self.fresh(self.nest.get(bid))  # a block split in a container stays in it
        if at_start:
            self.bids[self.cy] = new
        else:
            i = self.cy + 1
            while i < len(self.bids) and self.bids[i] == bid:
                self.bids[i] = new
                i += 1
        self.cy += 1
        self.cx = 0

    def nest_in(self) -> None:
        """Ctrl+Enter: like Enter, but a level down. The block splits at the
        cursor and becomes a container (it keeps its id, box and number): its
        text before the cursor one block inside it, the rest another, the
        cursor at the start of that one. One undo takes it all back, the
        store included."""
        if not self.self_id or self.pasting:
            self.line_break()
            return False
        if self.vmode:
            self.message = "not in a masked view"
            return False
        bid = self.bids[self.cy]
        if self.dirty():
            self.save()  # (so the block is in the store, to hold the others)
        self.refresh_library()
        made = {}
        if bid not in self.library:  # (not saved: empty) loose for now, the save takes it in
            made[bid] = store.new_block(bid, "")
        kept = store.subtree(self.library, self.cur_id) if self.cur_id in self.library else []
        undo = {"blocks": {**{i: None for i in made}, **{i: copy.deepcopy(self.library[i]["block"]) for i in kept}}}
        if made:
            try:
                store.restore({"blocks": made}, tidy=False)
            except (store.StoreError, OSError, ValueError) as e:
                self.message = str(e)
                return False
        self.step(undo)
        top, last = self.block_at(self.cy)
        line = self.lines[self.cy]
        head, tail = self.fresh(bid), self.fresh(bid)
        self.lines[self.cy:self.cy + 1] = [line[:self.cx], line[self.cx:]]
        self.bids[top:last + 1] = [head] * (self.cy - top + 1) + [tail] * (last - self.cy + 1)
        self.cy += 1
        self.cx = 0
        if made:
            self.refresh_library()
        return True

    def room_here(self) -> bool:
        """An empty line at the cursor for a block put in there (a quote, a
        picture): an empty line is one already (in a block, the block splits
        around it); at a block's very start, a new block above it; at its
        very end, one below; anywhere else in its text the block splits at
        the cursor and holds it, a level down (nest_in), the text either
        side. What's put in joins this undo step. Whether there's room."""
        line = self.lines[self.cy]
        if not self.self_id or self.on_atom() or not line.strip():
            return True  # (after a quote or image: it goes below)
        top, last = self.block_at(self.cy)
        if (self.cx == 0 and self.cy == top) or (self.cx == len(line) and self.cy == last):
            self.checkpoint("newline", force=True)
            at = self.cy if self.cx == 0 else last + 1
            self.lines.insert(at, "")
            self.bids.insert(at, self.fresh(self.outer(self.cy)))
            self.cy, self.cx = at, 0
        else:
            bid = self.bids[self.cy]
            if not self.nest_in():
                return False
            self.lines.insert(self.cy, "")
            self.bids.insert(self.cy, self.fresh(bid))
        self.joining = True
        return True

    def step_out(self) -> bool:
        """Enter on an empty block inside a container: it moves out a level,
        to just after the container. Whether it did."""
        bid = self.bids[self.cy]
        outer = self.nest.get(bid)
        top, last = self.block_at(self.cy) if bid else (self.cy, self.cy)
        if bid is None or outer is None or top != last or self.lines[self.cy].strip():
            return False
        self.checkpoint("newline", force=True)
        end = self.cy  # the container's last line
        for i in range(len(self.lines)):
            if outer in self.containers(i):
                end = i
        line = self.lines.pop(self.cy)
        self.bids.pop(self.cy)
        end -= 1  # (it was one of them)
        self.lines.insert(end + 1, line)
        self.bids.insert(end + 1, bid)
        if self.nest.get(outer):
            self.nest[bid] = self.nest[outer]
        else:
            del self.nest[bid]
        self.cy, self.cx = end + 1, 0
        return True

    def slash_opens(self) -> bool:
        """Whether a / typed here opens the menu of things to put in: at the
        start of a line or after a space (so and/or, paths and links type
        as text), with nothing selected, and something to put in here."""
        line = self.lines[self.cy]
        return (self.selection() is None and not self.is_atom(self.cy)
                and (self.cx == 0 or line[self.cx - 1].isspace()) and bool(self.commands(True)))

    def join_lines(self, i: int) -> None:
        """Join line i+1 onto line i. Across a block boundary the blocks merge:
        the rest of the lower block joins the upper one."""
        lower, upper = self.bids[i + 1], self.bids[i]
        self.lines[i:i + 2] = [self.lines[i] + self.lines[i + 1]]
        del self.bids[i + 1]
        self.relabel(lower, upper, i + 1)

    def relabel(self, old, new, i: int) -> None:
        """Lines from i on that are part of block `old` become part of `new`."""
        while old is not None and old != new and i < len(self.bids) and self.bids[i] == old:
            self.bids[i] = new
            i += 1

    def guard(self, col: int) -> bool:
        """Whether the character at `col` on this line is a mask's mark, which
        typing can't remove (it stands for hidden text, or is an anchor)."""
        line = self.lines[self.cy]
        if 0 <= col < len(line) and line[col] in MARKS:
            self.message = ("hidden text · space edits the mask" if line[col] == ELLIPSIS
                            else "a bracket · Backspace after it takes it out")
            return True
        return False

    def backspace(self) -> None:
        if self.cx > 0 and self.guard(self.cx - 1):
            return
        if self.cx == 0 and self.cy > 0 and self.lines[self.cy - 1].endswith(ELLIPSIS) and self.vmode:
            self.message = "hidden text · space edits the mask"  # the break is part of the hidden stretch
            return
        if self.cx == 0 and self.cy == 0:
            return
        if self.cx == 0 and self.is_atom(self.cy - 1):
            # don't merge text into a quote: drop an empty line, then land on the quote
            if self.lines[self.cy] == "":
                self.checkpoint("delete", force=True)
                del self.lines[self.cy]
                del self.bids[self.cy]
            self.cy -= 1
            return
        self.checkpoint("delete")
        if self.cx > 0:
            line = self.lines[self.cy]
            self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
            self.cx -= 1
        else:
            prev = self.lines[self.cy - 1]
            self.join_lines(self.cy - 1)
            self.cy -= 1
            self.cx = len(prev)

    def delete(self) -> None:
        line = self.lines[self.cy]
        if self.guard(self.cx):
            return
        if self.cx == len(line) and line.endswith(ELLIPSIS) and self.vmode and self.cy + 1 < len(self.lines):
            self.message = "hidden text · space edits the mask"  # the break is part of the hidden stretch
            return
        if self.cx == len(line) and self.cy == len(self.lines) - 1:
            return
        if self.cx == len(line) and self.is_atom(self.cy + 1):
            if line == "":
                self.checkpoint("delete", force=True)
                del self.lines[self.cy]
                del self.bids[self.cy]
            else:
                self.cy += 1
            self.cx = 0
            return
        self.checkpoint("delete")
        if self.cx < len(line):
            self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
        else:
            self.join_lines(self.cy)

    def delete_word(self) -> None:
        if self.cx == 0:
            self.backspace()
            return
        line = self.lines[self.cy]
        start = word_left(line, self.cx)
        start = max([start] + [i + 1 for i in range(start, self.cx) if line[i] in MARKS])  # stop at a mark
        if start == self.cx:
            self.guard(self.cx - 1)
            return
        self.checkpoint("delete", force=True)
        self.lines[self.cy] = line[:start] + line[self.cx:]
        self.cx = start

    def remove_quote(self) -> None:
        self.checkpoint("delete", force=True)
        del self.lines[self.cy]
        del self.bids[self.cy]
        if not self.lines:
            self.lines, self.bids = [""], [None]
        self.cy = min(self.cy, len(self.lines) - 1)
        self.cx = 0

    def open_after_quote(self) -> None:
        """Typing on a quote: start a new line below it (one undo step with the typing)."""
        self.checkpoint("newline", force=True)
        self.lines.insert(self.cy + 1, "")
        self.bids.insert(self.cy + 1, None)  # below a quote: a new block
        self.cy += 1
        self.cx = 0
        self.joining = True

    def own_quote(self, line: str) -> str:
        """A pasted quote line: kept as is if it's this block's own quote (moved
        within it), else a new quote of the same block."""
        m = QUOTE_RE.fullmatch(line)
        if not m or (m.group(2) and m.group(2) in store.subtree(self.library, self.cur_id)
                     and not any(l == line for l in self.lines)):
            return line
        return quote_line(m.group(1), self.fresh())

    def insert_quote(self, ref: str) -> None:
        """A quote of `ref` at the cursor (room_here), in place of the empty
        line there; continue below it."""
        if not self.room_here():
            return
        self.checkpoint("quote", force=True)
        self.lines[self.cy] = quote_line(ref, self.fresh(self.outer(self.cy)))
        self.bids[self.cy] = None
        if not (self.cy + 1 < len(self.lines) and not self.is_atom(self.cy + 1)):
            self.lines.insert(self.cy + 1, "")
            self.bids.insert(self.cy + 1, None)
        self.cy += 1
        self.cx = 0


    # --- undo ---------------------------------------------------------
    def undo_entry(self, record=None) -> tuple:
        """A step to come back to: the buffer as it is now, how it's shown (a
        masked view, a mask being edited), copies of the quotes and images in
        it (so one deleted comes back mask and all), and `record`, what to put back in
        the store with it."""
        quotes = {}
        for line in self.lines:
            i = atom_id(line)
            if i in self.library:
                quotes[i] = copy.deepcopy(self.library[i]["block"])
        mode = (copy.deepcopy(self.vmode), replace(self.medit) if self.medit else None)
        return (list(self.lines), list(self.bids), self.cy, self.cx,
                {"mode": mode, "quotes": quotes, "store": record, "nest": dict(self.nest)})

    def push_undo(self, record=None) -> None:
        """A new step on the undo stack, the buffer as it is now; redo is gone."""
        self.undo.append(self.undo_entry(record))
        del self.undo[:-UNDO_LIMIT]
        self.redo.clear()

    def step(self, record=None) -> None:
        """Mark an undo step (for an action that changes the store too, its
        `record`). After `joining` (an action that's the first half of this
        one) it joins that step instead: one undo takes back both, the store
        as it was before the first."""
        if self.joining and self.undo:
            self.joining = False
            if record:
                extra = self.undo[-1][4]
                earlier = (extra["store"] or {}).get("blocks", {})
                extra["store"] = {"blocks": {**record["blocks"], **earlier}}
        else:
            self.push_undo(record)
        self.last_edit = None
        self.stale = True

    def after_store_change(self) -> None:
        """The store changed under the buffers here (by an undo): re-read it."""
        self.refresh_library()
        for ref in [self.cur_id] + [f.id for f in self.stack]:
            if ref in self.library:
                self.base[ref] = store.content_hash(self.library, ref)
        self.stale = True

    def restore(self, undoing: bool) -> None:
        """^Z / ^Y: one step back (or forward), the buffer and whatever that
        step changed in the store with it, as if it had never happened."""
        stack = self.undo if undoing else self.redo
        if not stack:
            self.message = "nothing to undo" if undoing else "nothing to redo"
            return
        lines, bids, cy, cx, extra = stack.pop()
        inverse = None
        if extra["store"] is not None:
            if self.dirty():
                self.save()
            try:
                inverse = store.restore(extra["store"])
            except (store.StoreError, OSError, ValueError) as e:
                stack.append((lines, bids, cy, cx, extra))
                self.message = str(e)
                return
        (self.redo if undoing else self.undo).append(self.undo_entry(inverse))
        self.lines, self.bids, self.cy, self.cx = lines, bids, cy, cx
        self.nest = dict(extra["nest"])
        self.vmode = copy.deepcopy(extra["mode"][0])
        self.medit = replace(extra["mode"][1]) if extra["mode"][1] else None
        if self.medit:  # masking: the mask as it was, drawn and stored everywhere
            self.lines, self.bids = lines, bids
            self.mask_draw()
            self.save_mask()
        shown = set(map(atom_id, lines))
        gone = {q: b for q, b in extra["quotes"].items() if q in shown and q not in self.library}
        if gone:  # quotes deleted since: back as they were, until the buffer's saved
            store.restore({"blocks": gone}, tidy=False)
        if inverse is not None or gone:
            self.after_store_change()
        self.anchor = self.picked = None
        self.last_edit = None
        self.stale = True

    # --- selection and clipboard ---------------------------------------
    def selection(self):
        """Ordered ((line, col), (line, col)) of the selection, or None."""
        if self.anchor is None or self.anchor == (self.cy, self.cx):
            return None
        return tuple(sorted([self.anchor, (self.cy, self.cx)]))

    def selected_text(self, sel) -> str:
        (y1, x1), (y2, x2) = sel
        if y1 == y2:
            return self.lines[y1][x1:x2]
        return "\n".join([self.lines[y1][x1:], *self.lines[y1 + 1:y2], self.lines[y2][:x2]])

    def delete_selection(self, sel, replacing: bool = False) -> None:
        """Remove the selected text. When `replacing`, the edit that follows
        (typing, Enter, paste) joins the same undo step."""
        self.checkpoint("delete", force=True)
        (y1, x1), (y2, x2) = sel
        if y2 > y1 and x2 == 0 and self.is_atom(y2):
            y2, x2 = y2 - 1, len(self.lines[y2 - 1])  # stop before a quote, don't glue it to text
        lower = self.bids[y2]
        kept = "".join(c for c in self.selected_text(((y1, x1), (y2, x2))) if c in MARKS)  # hidden text stays
        self.lines[y1:y2 + 1] = [self.lines[y1][:x1] + kept + self.lines[y2][x2:]]
        del self.bids[y1 + 1:y2 + 1]
        self.relabel(lower, self.bids[y1], y1 + 1)  # what's left of the last block joins the first
        self.cy, self.cx = y1, x1
        self.anchor = None
        self.joining = replacing

    def select_all(self) -> None:
        if self.pick_all():  # more than one block: all of them, whole
            return
        self.anchor = (0, 0)
        self.cy = len(self.lines) - 1
        self.cx = len(self.lines[self.cy])

    def copy(self) -> None:
        if self.picked_lines():  # blocks selected whole (fw_blocks)
            self.copy_blocks()
            return
        sel = self.selection()
        if sel is None:
            self.message = "nothing selected"
            return
        text = "".join(SHOW.get(c, c) if c == ELLIPSIS else c for c in self.selected_text(sel) if c not in (CLOSE, OPEN))
        self.to_clipboard(text)
        store.save_clip({"text": text, "links": self.span_links(sel)} if self.rich() else None)
        self.message = "copied"

    def rich(self) -> bool:
        """What's copied here keeps its data (the rich clipboard): not in a
        masked view or while masking, whose text isn't the block's own."""
        return bool(self.self_id) and self.vmode is None and self.medit is None

    def block_at(self, y: int) -> tuple:
        """The block of text line `y` is in: (its first line, its last)."""
        top = end = y
        while top > 0 and self.bids[top - 1] == self.bids[y]:
            top -= 1
        while end + 1 < len(self.lines) and self.bids[end + 1] == self.bids[y]:
            end += 1
        return top, end

    def offset_in_block(self, y: int, x: int) -> int:
        top, _ = self.block_at(y)
        return sum(len(l) + 1 for l in self.lines[top:y]) + x

    def span_links(self, sel) -> list:
        """The hyperlinks in selection `sel`, inside one block of text (none
        across blocks, or over a mask's marks), as spans of the selected text."""
        (y1, x1), (y2, x2) = sel
        if self.bids[y1] is None or any(self.bids[y] != self.bids[y1] for y in range(y1, y2 + 1)) \
                or any(c in MARKS for c in self.selected_text(sel)):
            return []
        a, b = self.offset_in_block(y1, x1), self.offset_in_block(y2, x2)
        _, _, spans = self.block_links(self.lines, self.bids, self.block_at(y1)[0])
        return [{"to": to, "at": [max(s, a) - a, min(e, b) - a]} for s, e, to, _ in spans if s < b and e > a]

    def to_clipboard(self, text: str) -> None:
        self.clipboard = text
        try:
            subprocess.run(clipboard_tool(COPY_TOOLS), input=text.encode(), check=True,
                           env={**os.environ, "LANG": "en_US.UTF-8"})
        except (OSError, subprocess.CalledProcessError):
            pass

    def cut(self) -> None:
        if self.picked_lines():
            self.cut_blocks()
            return
        sel = self.selection()
        if sel is None:
            self.message = "nothing selected"
            return
        self.copy()
        self.delete_selection(sel)
        self.message = "cut"

    def read_clipboard(self) -> str:
        try:
            return subprocess.run(clipboard_tool(PASTE_TOOLS), capture_output=True, check=True,
                                  env={**os.environ, "LANG": "en_US.UTF-8"}).stdout.decode()
        except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
            return self.clipboard

    def paste_static(self) -> None:
        """^⇧V: blocks copied whole come back as static copies (fw_blocks)."""
        self.paste(static=True)

    def paste(self, static: bool = False) -> None:
        text = self.read_clipboard()
        if not text:
            return
        clip = store.load_clip() if self.rich() else None
        clip = clip if clip and clip.get("text") == text else None  # (copied here last, not elsewhere since)
        if clip and "blocks" in clip:  # blocks copied whole: quotes of them, moved back if cut, or copies
            units = clip["blocks"]
            self.paste_blocks(units, "static" if static else "move" if clip.get("cut") and self.movable(units) else "quote")
            return
        if self.picked is not None:
            self.replace_blocks()  # (one step with the paste)
        self.checkpoint("paste", force=True)
        text = "".join(c for c in text if c not in MARKS)
        parts = [self.own_quote(p) for p in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        line = self.lines[self.cy]
        head, tail = line[:self.cx], line[self.cx:]
        parts[0] = head + parts[0]
        self.cx = len(parts[-1]) if len(parts) > 1 else len(parts[0])
        parts[-1] += tail
        at = (self.cy, len(head))
        self.lines[self.cy:self.cy + 1] = parts
        self.bids[self.cy + 1:self.cy + 1] = [self.bids[self.cy]] * (len(parts) - 1)
        self.cy += len(parts) - 1
        if clip and clip.get("links") and self.bids[at[0]] is not None:
            self.paste_links(at, clip["links"])

    def paste_links(self, at: tuple, links: list) -> None:
        """The hyperlinks of text just pasted at `at` (line, column), onto it,
        in the same undo step as the paste (its record, to take them off)."""
        y = at[0]
        top, last = self.block_at(y)
        off, bid = self.offset_in_block(*at), self.bids[y]
        self.save()
        ref = bid if bid in self.library else self.cur_id  # (a block of plain text has no child for its text)
        if self.dirty() or not isinstance(self.library.get(ref, {}).get("content"), str):
            return  # not saved, or not a block of text in the store: the text alone
        try:
            record = store.add_links(ref, "\n".join(self.lines[top:last + 1]),
                                     [{"to": l["to"], "at": [l["at"][0] + off, l["at"][1] + off]} for l in links])
        except store.StoreError:
            return
        self.join_step(record)
        self.refresh_library()
        self.stale = True

    def join_step(self, record: dict) -> None:
        """What `record` puts back in the store, undone with the last step
        (what that step's edit made the store do), else a step of its own."""
        if not self.undo:
            self.step(record)
            return
        extra = self.undo[-1][4]
        extra["store"] = {"blocks": {**record["blocks"], **extra["store"]["blocks"]}} if extra["store"] else record

    def refresh_library(self) -> bool:
        """Re-read the store if it changed since we last looked, so quotes show
        their blocks' current text. Returns True when it reloaded."""
        if not self.self_id:
            return False
        try:
            mtime = store.DATA_PATH.stat().st_mtime_ns
            if mtime == self.store_mtime:
                return False
            self.library = store.build_library(store.load_data())
        except (OSError, ValueError):  # missing or unreadable: try again next tick
            return False
        self.store_mtime = mtime
        self.stale = True
        return True

    def resync_view(self) -> None:
        """After a save through the lens: if the stored view's shape changed
        (a hidden stretch emptied, ranges merged), show it as it now is."""
        mask = self.view_mask()
        if mask is None:
            return
        text = store.view(block_draft(self.library, self.cur_id), mask, self.vmode.opened)
        line = self.lines[self.cy]
        k = line.rfind(ELLIPSIS, 0, self.cx)
        if text != self.draft() and k >= 0 and line[k + 1:] and self.cy + 1 < len(self.lines):
            # typed after a … that ends its line: it went to the start of the next line
            cy, cx = self.cy, self.cx
            self.load_view(self.vmode.qid, mask, self.vmode.opened, clear=False)
            if self.cy + 1 < len(self.lines) and self.lines[cy].endswith(ELLIPSIS):
                self.cy, self.cx = cy + 1, min(cx - k - 1, len(self.lines[cy + 1]))
            return
        marks = [c for c in text if c in MARKS]
        if marks != [c for line in self.lines for c in line if c in MARKS]:
            opened = self.vmode.opened if self.vmode.opened in store.holes(
                block_draft(self.library, self.cur_id), mask) else None
            cy, cx = self.cy, self.cx
            self.load_view(self.vmode.qid, mask, opened)
            self.cy = min(cy, len(self.lines) - 1)
            self.cx = min(cx, len(self.lines[self.cy]))

    def follow_store(self) -> None:
        """If the block being edited changed in another session and has no
        unsaved edits here, show its new text (instead of saving over it later)."""
        ref = self.cur_id
        if self.medit or self.base.get(ref) is None or ref not in self.library or (self.lines, self.bids) != self.saved:
            return
        now = store.content_hash(self.library, ref)
        if now == self.base[ref]:
            return
        if self.vmode and self.view_mask() is not None:
            self.load_view(self.vmode.qid, self.view_mask(), None)
        else:
            self.vmode = None
            self.load_text(block_draft(self.library, ref))
            self.saved = self.snapshot()
        self.base[ref] = now
        self.cy = min(self.cy, len(self.lines) - 1)
        self.cx = min(self.cx, len(self.lines[self.cy]))
        self.anchor = self.picked = None
        self.message = "updated from another session"

    # --- visits (fw_block.attend; schema v15) -------------------------
    def attend(self, ids, flags: str, at: float) -> None:
        self.visits.live, seen = store.attend(self.visits.live, ids, flags, at)
        self.visits.pending = store.note_visits(self.visits.pending, seen)

    def visit_open(self) -> None:
        """The open pericope was opened (or come back to, along the trail);
        the cursor's time in the block it's in starts now."""
        if self.self_id:
            now = store.clock()
            self.attend([self.self_id], "o", now)
            bid = self.cursor_block()
            self.visits.here = (bid, now, False, None) if bid else None

    def cursor_block(self) -> str | None:
        """The block the cursor's in: a block of text, or a picture; not a
        quote selected whole (only seen), nor while in the menu or header."""
        if not self.self_id or self.mode in ("menu", "header") or not 0 <= self.cy < len(self.bids):
            return None
        m = IMAGE_RE.fullmatch(self.lines[self.cy]) if self.bids[self.cy] is None else None
        return self.bids[self.cy] or (m.group(1) if m else None)

    def carried(self, bid: str) -> list:
        """`bid` and each block it's part of, up to its entry (as `updated`
        goes; not through quotes): its containers here, the block being
        edited, and what that's inside in the store."""
        blocks = {i: e["block"] for i, e in self.library.items()}
        out = [bid, *reversed(self.containers(self.cy)), self.cur_id, *store.ancestors(blocks, self.cur_id)]
        return list(dict.fromkeys(i for i in out if i))

    def visit_tick(self, key: bool = False, wrote: bool = False) -> None:
        """After a key (`wrote`: it changed the text) or an idle tick: any key
        is attention on the open pericope; the block the cursor's in counts
        once it's stayed VISIT_DWELL or been written in, and each key in it
        after that keeps its visit going. Visits that ended are written."""
        if not self.self_id:
            return
        now, v = store.clock(), self.visits
        if key:
            self.attend([self.self_id], "o", now)
        bid = self.cursor_block()
        if bid is None or not v.here or v.here[0] != bid:
            v.here = (bid, now, False, None) if bid else None
        if v.here:
            bid, since, counted, chain = v.here
            if wrote or (key and counted) or (not counted and now - since >= store.VISIT_DWELL):
                chain = chain or self.carried(bid)
                self.attend(chain, "c" + "w" * wrote + "q" * bool(self.stack), now if counted else since)
                v.here = (bid, since, True, chain)
        if store.ended(v.live, now) & v.pending.keys():
            self.flush_visits()

    def flush_visits(self) -> None:
        """Write the visits seen so far into the store (kept to try again if it refuses)."""
        if not self.visits.pending:
            return
        try:
            store.record_visits(self.visits.pending)
        except (store.StoreError, OSError):
            return
        self.visits.pending = {}
        now = store.clock()
        self.visits.live = {i: x for i, x in self.visits.live.items() if now - x[1] <= store.VISIT_GAP}

    def snapshot(self) -> tuple:
        return list(self.lines), list(self.bids)

    def draft(self) -> str:
        if not self.self_id:
            return "\n".join(self.lines)
        return format_draft(self.lines, self.bids, self.silent(), self.nest)

    def load_text(self, text: str, taken=None) -> None:
        """Make the buffer draft `text`: its lines, their blocks, their nesting."""
        self.lines, self.bids = parse_draft(text, self.taken() if taken is None else taken)
        self.nest = parse_nest(text)

    def outer(self, li: int, lines=None, bids=None, nest=None) -> str | None:
        """The block line `li` is nested in (a container), if any: its text
        block's, or its quote's (of this buffer, or the ones given)."""
        lines, bids, nest = lines or self.lines, bids or self.bids, self.nest if nest is None else nest
        return nest.get(atom_id(lines[li]) if bids[li] is None else bids[li])

    def containers(self, li: int) -> tuple:
        """The containers line `li` is in, outermost first."""
        return chain(self.nest, atom_id(self.lines[li]) if self.bids[li] is None else self.bids[li])[::-1]

    def silent(self) -> set:
        """Blocks in the buffer with no marker of their own in its text (in a
        masked view, or masking one: theirs is hidden)."""
        return (self.medit and self.medit.silent) or (self.vmode and self.vmode.silent) or set()

    def draft_offsets(self) -> list:
        """Where each line starts in draft() (marker lines counted)."""
        offs, pos, prev = [], 0, None
        silent = self.silent()
        for line, bid in zip(self.lines, self.bids):
            if bid is not None and bid != prev and bid not in silent:
                pos += len(block_line(bid, chain(self.nest, bid))) + 1
            offs.append(pos)
            pos += len(atom_draft(line, self.nest) if bid is None else line) + 1
            prev = bid
        return offs

    def taken(self) -> set:
        """Ids in use: in the store, and in every buffer open here."""
        return set(self.library) | set(self.bids) | {b for f in self.stack for b in f.bids}

    def fresh(self, outer: str | None = None) -> str:
        """A new block id, nested in `outer` if given."""
        i = store.new_id(self.taken())
        if outer:
            self.nest[i] = outer
        return i

    def tidy_bids(self) -> None:
        """Keep each line's block in step with the lines after an edit: a quote
        line is no block of text; a text line with none joins the block above
        it, or starts a new one below a quote; and a block's lines stay
        together, so one split apart (a quote put in its middle) carries on
        below under a new id."""
        seen, prev, outer = set(), None, None
        for i, line in enumerate(self.lines):
            if is_atom(line):
                self.bids[i] = prev = None
                outer = self.outer(i)
                continue
            bid = self.bids[i] or prev
            if bid is None or (bid != prev and bid in seen):
                bid = self.fresh(outer)  # (in the container the line above is in)
            self.bids[i] = prev = bid
            outer = self.nest.get(bid)
            seen.add(bid)
        self.fold()

    def fold(self) -> None:
        """A container holding just one block is that block again, as the
        store has it (set_container): one block of text folds back into it
        (its lines the container's, which keeps its id), and one container's
        blocks move up into it. Not quotes or pictures: those keep their box.
        Not in a masked view, whose nesting is partly hidden."""
        if self.vmode or self.medit:
            return
        while True:
            kids = {}  # container -> the blocks directly in it, in order
            for i, line in enumerate(self.lines):
                key = atom_id(line) if self.bids[i] is None else self.bids[i]
                path = tuple(self.containers(i)) + (key,)
                for c, child in zip(path, path[1:]):
                    ks = kids.setdefault(c, [])
                    if not ks or ks[-1] != child:
                        ks.append(child)
            one = next(((c, ks[0]) for c, ks in kids.items() if len(ks) == 1
                        and (ks[0] in kids or ks[0] in self.bids)), None)
            if one is None:
                return
            c, k = one
            if k in kids:  # a container: its blocks move up into c
                for x, v in list(self.nest.items()):
                    if v == k:
                        self.nest[x] = c
            else:  # a block of text: its lines are c's
                self.bids = [c if b == k else b for b in self.bids]
            self.nest.pop(k, None)

    def meta_values(self) -> list[str]:
        return [f.get("value", "") for f in self.editable]

    def dirty(self) -> bool:
        return (self.lines, self.bids) != self.saved or (not self.stack and self.meta_values() != self.saved_meta)

    def save(self) -> None:
        """The draft file first (so the writing is safe on disk), then the
        store. Text the store refused stays unsaved here, so it's retried."""
        self.tidy_bids()
        if self.stack:  # inside a quote: the text belongs to that block's entry
            notes, ok = self.commit(self.cur_id, [])
        else:
            draft = self.draft()
            write_file(self.path, draft)
            notes, ok = self.commit(self.self_id, self.meta["fields"]) if self.self_id else ([], True)
            if self.meta_path:
                self.meta["base"] = self.base.get(self.self_id)
                if ok:
                    self.meta["synced"] = store.draft_digest(draft)  # `end` needn't save this again
                write_file(self.meta_path, json.dumps(self.meta, indent=2, ensure_ascii=False) + "\n")
            if ok:
                self.saved_meta = self.meta_values()
        if ok:
            self.saved = self.snapshot()
        self.refused = not ok  # retried, but not at once
        if notes:
            self.message = notes[-1]

    def commit(self, ref: str, fields: list) -> tuple[list[str], bool]:
        """Save block `ref` from this buffer into the store: (notes, whether it went in)."""
        try:
            if self.medit and ref == self.cur_id:  # masking: only the brackets change
                self.save_mask()
                return [], True
            if self.vmode and ref == self.cur_id:  # a masked quote: through the lens
                self.base.update(store.commit_view(self.vmode.qid, self.draft(), self.vmode.opened,
                                                   base=self.base.get(ref), seen=self.view_mask()))
                self.refresh_library()
                self.resync_view()
                return [], True
            notes, self.base[ref], record = store.commit(ref, self.draft(), fields, base=self.base.get(ref))
            if record:  # blocks taken out, quoted elsewhere: their quotes became text; undo puts them back
                self.join_step(record)
        except store.StoreError as e:
            return [str(e)], False
        except (OSError, ValueError) as e:
            return [f"store not updated: {e}"], False
        return notes, True

    # --- mouse --------------------------------------------------------
    def mouse(self) -> None:
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return
        self.ensure_layout()
        if bstate & curses.BUTTON4_PRESSED or bstate & WHEEL_DOWN:
            step = -WHEEL_ROWS if bstate & curses.BUTTON4_PRESSED else WHEEL_ROWS
            if self.fedit is None:
                self.anchor = None
                self.move_vert(step)
            return
        if not bstate & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
            return
        if HEADER_TOP <= my < HEADER_TOP + len(self.editable):  # an editable header line
            while self.stack:
                self.leave()
            self.enter_field(my - HEADER_TOP)
            v = self.fedit.text
            col, x = 0, 0
            while col < len(v) and x + cwidth(v[col]) <= mx - self.value_x:
                x += cwidth(v[col])
                col += 1
            self.fedit.x = col
        elif self.top <= my < self.top + self.text_h:
            self.fedit = None
            self.anchor = None
            self.last_edit = None
            row = self.scroll + my - self.top
            if row >= len(self.rows):  # below the text: go to the entry's end
                while self.stack:
                    self.leave()
                self.cy = len(self.lines) - 1
                self.cx = len(self.lines[self.cy])
            else:
                self.goto_row(row, max(mx - self.text_x(row), 0), click=True)


    # --- header -------------------------------------------------------
    def edit_field(self, act: str | None) -> None:
        """Apply one action (bound in the "header" context) while the cursor is
        in a header field."""
        f, e = self.editable[self.fedit.index], self.fedit
        v = e.text
        if act == "open_field":
            if f.get("derived"):
                self.open_backlinks()
                return
            act = "next_field"
        if f.get("derived") and act not in ("next_field", "leave_field", "prev_field"):
            return  # (worked out, not written: nothing to type)
        if act in ("next_field", "leave_field"):
            if act == "next_field" and e.index < len(self.editable) - 1:
                self.enter_field(e.index + 1)
            else:
                self.fedit = None  # back to the text, where the cursor was
            return
        if act == "prev_field":
            if e.index > 0:
                self.enter_field(e.index - 1)
            return
        if act == "select_all":
            e.anchor, e.x = 0, len(v)
            return
        sel = sorted((e.anchor, e.x)) if e.anchor is not None and e.anchor != e.x else None
        e.anchor = None
        if sel and (act in ("backspace", "delete", "delete_word", "paste") or (act is not None and len(act) == 1)):
            v, e.x = v[:sel[0]] + v[sel[1]:], sel[0]  # the selection goes; typing or a paste takes its place
            if act in ("backspace", "delete", "delete_word"):
                act = None
        if act in ("left", "word_left"):
            e.x = max(e.x - 1, 0) if act == "left" else word_left(v, e.x)
        elif act in ("right", "word_right"):
            e.x = min(e.x + 1, len(v)) if act == "right" else word_right(v, e.x)
        elif act == "home":
            e.x = 0
        elif act == "end":
            e.x = len(v)
        elif act == "backspace" and e.x > 0:
            v, e.x = v[:e.x - 1] + v[e.x:], e.x - 1
        elif act == "delete_word":
            start = word_left(v, e.x)
            v, e.x = v[:start] + v[e.x:], start
        elif act == "delete":
            v = v[:e.x] + v[e.x + 1:]
        elif act == "paste":
            text = self.read_clipboard().replace("\r", "\n").split("\n")[0]
            v, e.x = v[:e.x] + text + v[e.x:], e.x + len(text)
        elif act is not None and len(act) == 1:
            v, e.x = v[:e.x] + act + v[e.x:], e.x + 1
        e.text = v
        f["value"] = e.was if v == e.start else v  # left as it was (a derived title stays derived); emptied, derived again

    def enter_field(self, i: int) -> None:
        """Into header field `i`, the cursor at its end: what it shows (a
        derived title too) is the text to edit."""
        f = self.editable[i]
        self.fedit = FieldEdit(i, len(self.shown(f)), self.shown(f), self.shown(f), f.get("value") or "")

    def backlinks(self) -> list:
        """The blocks pointing at the open entry (fw_block.backlinks), worked
        out again when the store changes."""
        if self.found[0] != self.store_mtime:
            blocks = {i: e["block"] for i, e in self.library.items()}
            self.found = (self.store_mtime, store.backlinks(blocks, self.self_id) if self.self_id in blocks else [])
        return self.found[1]

    def hint(self, f: dict) -> str:
        """What an empty field stands in with, e.g. the title derived from the text."""
        if f.get("derived"):
            return store.backlink_summary(self.backlinks())
        return (PLACEHOLDERS[f["key"]](self.root_lines()) if f["key"] in PLACEHOLDERS else f.get("placeholder")) or ""

    def shown(self, f: dict) -> str:
        """A field's text as you edit it: what's written, else what's derived,
        so a derived title can be edited like a written one."""
        return f.get("value") or self.hint(f)

    def draw_header(self, scr, w: int) -> int:
        """Draw the metadata header; returns how many rows it used."""
        if not self.meta["fields"]:
            return 0
        fixed = [f for f in self.meta["fields"] if not f.get("editable") and f["key"] not in HIDDEN]
        for f in fixed:
            if f["key"] in LIVE:
                f["value"] = LIVE[f["key"]](self)
        # live fields first so they always show; long values last, where they get clipped
        fixed.sort(key=lambda f: (f["key"] not in LIVE, len(f.get("value") or "")))
        for f in fixed:
            if f["key"] == "paraphrases":  # (live, by title: the mark changes without reopening)
                source = store.paraphrases(self.library.get(self.self_id))
                f["value"] = self.library[source]["title"] if source in self.library else ""
        fixed = [f for f in fixed if f["key"] != "visits" or f.get("value")]  # (never visited: nothing to say)
        info = "  ·  ".join(f"{LABELS.get(f['key'], f['key'])} {PRETTY.get(f['key'], str)(f.get('value')) or '—'}"
                            for f in fixed)
        # in a box like a block of text's, its text at the column all text starts at
        x, room = self.text_x(0), self.inner()
        self.value_x = x + max((len(f["key"]) for f in self.editable), default=0) + 2
        put(scr, 1, x, info[:room], curses.A_DIM)
        for i, f in enumerate(self.editable, start=HEADER_TOP):
            put(scr, i, x, f["key"], curses.A_DIM)
            value = f.get("value", "")
            e = self.fedit if self.fedit is not None and self.fedit.index == i - HEADER_TOP else None
            if e is not None:  # being edited: its text as typed (empty stays empty), the selection reversed
                text = e.text[:max(x + room - self.value_x, 0)]
                a, b = sorted((e.anchor, e.x)) if e.anchor is not None else (0, 0)
                derived = e.text == e.start and not e.was
                put(scr, i, self.value_x, text, curses.A_DIM if derived else 0)
                if b > a:
                    put(scr, i, self.value_x + swidth(text[:a]), text[a:b], curses.A_REVERSE)
            elif value:
                put(scr, i, self.value_x, value[:max(x + room - self.value_x, 0)])
            else:
                put(scr, i, self.value_x, (self.hint(f) or "(none)")[:max(x + room - self.value_x, 0)], curses.A_DIM)
        rows = len(self.editable) + HEADER_TOP + 1
        lx, rx = self.gutter, self.cols - 2
        put(scr, 0, 0, "H".rjust(self.gutter - 1), curses.A_DIM)  # in the gutter, as a block's number
        put(scr, 0, lx, box_edge(rx - lx + 1, "top", False), self.ink.faint)
        for y in range(1, rows - 1):
            put(scr, y, lx, THIN[5], self.ink.faint)
            put(scr, y, rx, THIN[5], self.ink.faint)
        put(scr, rows - 1, lx, box_edge(rx - lx + 1, "bottom", False), self.ink.faint)
        return rows

    # --- screen -------------------------------------------------------
    def draw(self, scr) -> None:
        h, w = scr.getmaxyx()
        if (h, w) != self.screen_size:
            if self.screen_size is not None:
                self.resized_at = time.monotonic()
            if self.drawn:  # (the pictures are where they were: all of it repainted, once)
                scr.clearok(True)
                self.drawn = {}
            self.screen_size = (h, w)
        if w != self.cols:
            self.cols = w
            self.stale = True
        self.ensure_layout()
        scr.erase()
        top = self.top = self.draw_header(scr, w)
        self.text_h = max(h - 1 - top, 1)
        r = self.cursor_row()
        if r < self.scroll:
            self.scroll = r
            while self.scroll > 0 and self.is_gap(self.scroll - 1):
                self.scroll -= 1  # the box's top too, with the block's number
        elif r >= self.scroll + self.text_h:
            self.scroll = r - self.text_h + 1

        sel = self.selection()
        end_mark = self.selected_end()
        self.draw_rows(scr, top, sel, end_mark)

        if self.fedit is not None:
            where = self.editable[self.fedit.index]["key"]
        elif self.picked is not None:
            lo, hi = self.picked_span()
            where = f"block {lo + 1}" if lo == hi else f"blocks {lo + 1}–{hi + 1}"
        else:
            where = f"{self.cy + 1}:{self.cx + 1}"
        crumbs = "".join(f"  {t} ›" for t in self.trail)
        left = f" fw{crumbs}  {where}"
        if self.message:
            left += "  " + self.message
        ref, m = None, None  # the quote the cursor is on, else the one it's editing inside
        if self.fedit is None and not self.message:
            m = QUOTE_RE.fullmatch(self.lines[self.cy])
            ref = m.group(1) if m else (self.cur_id if self.stack else None)
            if self.medit:  # masking: the quote being masked, wherever the cursor is in it
                ref = store.quoted(self.library.get(self.medit.qid))[0]
        link = self.link_here() if self.fedit is None and not self.message and not m and not self.medit else None
        if link:  # on a hyperlink: the entry it points at
            ref = link[2]
        tag = f" {'↗ ' if link else ''}{self.library.get(ref, {}).get('title', 'missing block')} " if ref else ""
        help = HELP.replace("^Q quit", "^Q back") if self.trail else HELP
        hint = help if len(left) + 2 + len(tag) + len(help) < w else ""  # the quote's title wins
        bar = left + " " * max(w - len(left) - len(hint), 1) + hint
        put(scr, h - 1, 0, bar[:w - 1].ljust(w - 1), curses.A_REVERSE)
        if tag:  # on a quote: its title, tagged red like the bar
            put(scr, h - 1, len(left) + 2, tag[:max(w - 1 - len(left) - 2, 0)], self.ink.tag)

        if self.fedit is not None:
            y = HEADER_TOP + self.fedit.index
            x = self.value_x + swidth(self.fedit.text[:self.fedit.x])
            if self.palette is not None:  # (the backlinks list, under the header)
                y, x = self.draw_palette(scr, h, w, y, x)
        else:
            li, start, _, q, depth = self.rows[r]
            y = top + r - self.scroll
            if end_mark:  # a quote selected whole: its heavy edge shows where; no text cursor
                y, x = top + end_mark[0] - self.scroll, self.text_x(end_mark[0])
            else:
                x = self.text_x(r) + self.col_x(li, start, self.cx)
            ghost = self.next_stop()  # outlined: where one more press of the arrow lands
            if ghost and 0 <= ghost[0] - self.scroll < self.text_h:
                put(scr, top + ghost[0] - self.scroll, ghost[1], ghost[2], self.ink.ghost)
            if self.palette is not None:
                y, x = self.draw_palette(scr, h, w, y, x)
        self.place_pictures(scr, top)
        try:
            curses.curs_set(0 if end_mark else 1)
        except curses.error:
            pass  # a terminal that can't hide it
        try:
            scr.move(y, min(x, w - 1))
        except curses.error:
            pass

    def place_pictures(self, scr, top: int) -> None:
        """Which pictures to draw this frame: those wholly on screen (one cut
        off by the screen's edge says so instead), none while the menu's
        open. One already drawn where it is, its cells untouched, stays as it
        is; the rows a picture left are repainted whole (curses doesn't know
        it was there, and would leave what's left of it), and any picture on
        them is drawn again."""
        placed = []
        for r, cols, rows, name in ([] if self.palette is not None else self.pictures):
            y = top + r - self.scroll
            if top <= y and y + rows <= top + self.text_h:
                placed.append((y, text_column(self.gutter), cols, rows, name))
            elif y < top + self.text_h and y + rows > top:
                put(scr, max(y, top), text_column(self.gutter), "▣ scroll to see the picture", curses.A_DIM)
        cells = {p: tuple(scr.inch(y, x) for y in range(p[0], p[0] + p[3]) for x in range(p[1], p[1] + p[2]))
                 for p in placed}
        left = [p for p in self.drawn if self.drawn[p] != cells.get(p)]
        for y, _, _, rows, _ in left:
            scr.redrawln(y, rows)
        gone = {y for p in left for y in range(p[0], p[0] + p[3])}
        self.drawn = {p: cells[p] for p in placed if p in self.drawn and p not in left
                      and not gone & set(range(p[0], p[0] + p[3]))}
        self.to_draw = {p: c for p, c in cells.items() if p not in self.drawn}

    def show_pictures(self) -> None:
        """Draw the pictures place_pictures chose, over the blank rows left
        for them, once curses has drawn the screen; not while the window's
        still changing size (edit_loop comes back once it's settled)."""
        if not self.to_draw or self.settling():
            return
        out = []
        for (y, x, cols, rows, name) in self.to_draw:
            esc = self.picture_escape(name, cols, rows)
            if esc:
                out.append(f"\x1b[{y + 1};{x + 1}H" + esc)
        self.drawn.update(self.to_draw)
        self.to_draw = {}
        if out:
            sys.stdout.write("\x1b7" + "".join(out) + "\x1b8")
            sys.stdout.flush()

    def settling(self) -> bool:
        return time.monotonic() - self.resized_at < SETTLE_MS / 1000

    def picture_escape(self, name: str, cols: int, rows: int) -> str | None:
        """The escape that draws picture `name` in `cols` × `rows` cells (made
        once): of a copy no wider than that needs, if the original's much
        bigger (fw_image.thumb_width). None if its file's gone."""
        key = (name, cols, rows)
        if key not in self.escapes:
            try:
                nbytes = store.image_file(name).stat().st_size
                data = store.picture_bytes(name, fw_image.thumb_width(self.picture_size(name), nbytes, cols))
            except OSError:
                return None
            self.escapes[key] = fw_image.iterm(data, cols, rows)
        return self.escapes[key]

    def handle(self, scr, key) -> bool:
        """Apply one key. Returns True when the editor should exit."""
        done = self.apply_key(scr, key)
        self.tidy_bids()
        return done

    def apply_key(self, scr, key) -> bool:
        """One key: what it is, then what it does in the mode the editor's in
        (fw_state), each mode handling its own keys and passing the rest on to
        a more general one. Returns True when the editor should close."""
        self.message = ""
        self.joining = False
        name = keys.decode(scr, key, self.prev_cr)
        if self.confirming:  # the answer to a question
            return self.confirm_key(name)
        act = keys.bind(name)
        self.prev_cr = key == "\r"
        if act == "paste_start":
            self.pasting, self.pasted = True, []
            return False
        if act == "paste_end":
            self.end_paste()
            return False
        if self.pasting:
            self.pasted.append((name, act))
            return False
        if act == "mouse":
            self.palette = self.picked = None  # a click closes the menu (and drops blocks selected whole), then acts
            self.mouse()
            self.goal_x = None
            if self.fedit is None and self.on_atom():
                self.cx = 0
            return False
        return getattr(self, "key_" + self.mode)(name, act)

    def end_paste(self) -> None:
        """A bracketed paste has ended: a picture file's path (what a terminal
        pastes for a file dropped on it) becomes an image block here; anything
        else is typed in, key by key, as a paste is."""
        text = "".join(n if len(n) == 1 else "" for n, _ in self.pasted)
        path = fw_image.dropped_path(text) if self.mode in ("text", "quote") and self.self_id else None
        if path and os.path.isfile(os.path.expanduser(path)):
            self.pasting = False
            self.insert_image(lambda: store.add_image(path))
            return
        for name, act in self.pasted:
            self.message, self.joining = "", False
            getattr(self, "key_" + self.mode)(name, act)
            self.tidy_bids()
        self.pasting, self.pasted = False, []

    def insert_image(self, add) -> None:
        """A picture as an image block at the cursor (room_here: in a block's
        text, nested there; after the quote or image the cursor is on), the
        cursor below it. `add()` puts the picture in the store's images folder and
        returns its name there (store.add_image, add_image_data); the block
        goes in loose and the save takes it in. One undo takes it back out."""
        if self.dirty():
            self.save()
        self.refresh_library()
        try:
            name = add()
        except (store.StoreError, OSError, ValueError) as e:
            self.message = str(e)
            return
        if not self.room_here():
            return
        try:
            iid = self.fresh(self.outer(self.cy))
            store.restore({"blocks": {iid: store.new_block(iid, {"image": name})}}, tidy=False)
        except (store.StoreError, OSError, ValueError) as e:
            self.message = str(e)
            return
        self.step({"blocks": {iid: None}})
        self.anchor = self.picked = None
        line, bid = self.lines[self.cy], self.bids[self.cy]
        if self.on_atom():
            at, below = self.cy + 1, []
        else:
            head, tail = line[:self.cx], line[self.cx:]
            at = self.cy + (1 if head else 0)
            self.lines[self.cy:self.cy + 1], self.bids[self.cy:self.cy + 1] = ([head], [bid]) if head else ([], [])
            below = [tail] if tail else []
        if not below and not (at < len(self.lines) and not self.is_atom(at)):
            below = [""]  # (a line to write on below it)
        self.lines[at:at] = [image_line(iid)] + below
        self.bids[at:at] = [None] + [bid] * len(below)  # (tidy_bids gives a split block's tail a new id)
        self.tidy_bids()
        self.cy, self.cx, self.unit_side = at + 1, 0, None
        self.refresh_library()
        self.save()  # (taking it in at once: nothing else erases it loose)
        self.message = "picture added"

    def fetching(self) -> bool:
        """Whether the menu's waiting on a picture to download."""
        return self.palette is not None and self.palette.fetch is not None

    def fetched(self) -> None:
        """If the picture the menu's waiting on has downloaded, it goes in at
        the cursor (insert_image) and the menu closes; if it couldn't be,
        the menu says why."""
        if not self.fetching() or self.palette.fetch["result"] is None:
            return
        p = self.palette
        ok, got = p.fetch["result"]
        p.fetch = None
        if ok and fw_image.kind(got[:16]) is None:
            ok, got = False, "that's not a png, jpeg, gif or webp"
        if not ok:
            p.note = got
            return
        self.palette = None
        self.insert_image(lambda: store.add_image_data(got, p.query))

    def quit(self) -> bool:
        if self.dirty():
            self.save()
        return True

    def key_menu(self, name: str, act) -> bool:
        if act == "quit":
            return self.quit()
        self.palette_key(keys.bind(name, "picker"))
        return self.opening is not None

    def key_header(self, name: str, act) -> bool:
        if act == "quit":
            return self.quit()
        self.edit_field(keys.bind(name, "header"))
        return False

    def key_masking(self, name: str, act) -> bool:
        if self.mask_key(name):
            return False
        return self.key_quote(name, act)

    def key_view(self, name: str, act) -> bool:
        if act == " " and self.selection() is None:  # Space on a …: mask it there
            col = self.mark_near(ELLIPSIS)
            if col is not None:
                draft = block_draft(self.library, self.cur_id)
                self.edit_mask(at=store.view_to_draft(draft, self.view_mask(), self.offset_at(self.cy, col)))
                return False
        return self.key_quote(name, act)

    def key_quote(self, name: str, act) -> bool:
        if act == "escape" and self.can_pick() and not self.on_atom():
            self.pick_here()  # the block you're in, whole (fw_blocks); Esc again: the quote
            return False
        if act == "escape":
            self.leave()  # select the quote as a unit
            self.unit_side = None
            return False
        if act == "up":
            self.ensure_layout()
            if self.at_top():
                self.leave()
                self.unit_side = "before"
                return False
        return self.key_text(name, act)

    def key_text(self, name: str, act) -> bool:
        if act == "escape" and self.can_pick() and not self.on_atom():
            self.pick_here()  # the block you're in, whole (fw_blocks)
            return False
        if act == "up" and self.editable:
            self.ensure_layout()
            going_in = self.on_atom() and self.unit_side == "after" and self.enterable(self.cy)
            if self.at_top() and not going_in:
                self.anchor = None
                self.enter_field(len(self.editable) - 1)
                return False
        if act == "/" and self.slash_opens():
            self.open_menu(True)
            return False
        if act == "palette":
            self.open_menu(False)
            return False
        if act in COMMAND_KEYS:
            self.command_key(act)
            return self.opening is not None
        selecting = act in SELECTING
        if selecting:
            act = SELECTING[act]
            if self.anchor is None:
                self.anchor = (self.cy, self.cx)
        elif act in MOVES:
            self.anchor = None
        sel = self.selection()
        if sel and act in ("backspace", "delete", "delete_word"):
            self.delete_selection(sel)
            act = None
        elif sel and act is not None and (len(act) == 1 or act in TYPING):
            self.delete_selection(sel, replacing=True)
        elif self.on_atom() and act in ("backspace", "delete", "delete_word"):
            self.remove_quote()
            act = None
        elif self.on_atom() and act is not None and (len(act) == 1 or act in TYPING):
            self.open_after_quote()  # a new block below the quote
            if act in ("newline", "line_break", "nest_in"):
                act = None
        if act in VERTICAL:
            before = len(self.stack)
            self.move_vert(VERTICAL[act] * (self.text_h if act.startswith("page") else 1))
            self.mask_flow(act, before)
        elif act in MOVES:
            before = len(self.stack)
            getattr(self, act)()
            self.mask_flow(act, before)
        elif act == "quit":
            return self.quit()
        elif act == "undo":
            if not self.undo and self.trail and not self.stack:
                if self.dirty():
                    self.save()
                return True  # nothing left since Open it: undo the step in, back out
            self.restore(True)
        elif act == "redo":
            self.restore(False)
        elif act in EDITS:
            getattr(self, act)()
        elif act == "tab":
            self.insert("\t")
        elif act is not None and len(act) == 1:
            self.insert(act)
        if act in MOVES:
            self.last_edit = None  # moving the cursor ends an undo group
        if act not in VERTICAL:
            self.goal_x = None
        if self.on_atom():
            self.cx = 0  # a quote has one cursor position
            if act in ("backspace", "delete"):
                self.unit_side = None  # selected from beside it, not by arrowing in
        else:
            self.unit_side = None
        if selecting:
            self.snap_to_blocks()  # reached another block: whole blocks
        return False


VERTICAL = {"up": -1, "down": 1, "page_up": -1, "page_down": 1}
MOVES = {"left", "right", "word_left", "word_right", "home", "end", *VERTICAL}
EDITS = {"newline", "line_break", "nest_in", "backspace", "delete", "delete_word",
         "select_all", "copy", "cut", "paste", "paste_static"}
# actions that put text in, as typing does (so they replace a selection)
TYPING = ("newline", "line_break", "nest_in", "paste", "paste_static", "tab")
# Shift + a move: extend the selection
SELECTING = {"select_" + m: m for m in MOVES}
COMMAND_KEYS = set(RUNS.values()) | {"delete_entry"}  # keys that run a menu command (fw_menu.command_key)


def run(scr, ed: Editor) -> None:
    ed.ink = setup(scr)
    with keyboard_modes():
        loop(scr, ed)


def write_file(path: str, text: str) -> None:
    """Write a file whole, never half: a kill mid-write leaves the old one."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


# The system clipboard: macOS's, else Wayland's or X's, whichever is installed.
COPY_TOOLS = (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])
PASTE_TOOLS = (["pbpaste"], ["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
               ["xsel", "--clipboard", "--output"])


def clipboard_tool(tools) -> list[str]:
    """The first of `tools` on PATH; OSError if none is (the editor then
    keeps its own clipboard)."""
    for tool in tools:
        if shutil.which(tool[0]):
            return tool
    raise OSError("no clipboard tool")


def pictures_here() -> bool:
    """Whether this terminal draws pictures (iTerm2's inline images, not
    through tmux); $FW_PICTURES=1 or 0 says so instead."""
    if os.environ.get("FW_PICTURES") in ("0", "1"):
        return os.environ["FW_PICTURES"] == "1"
    iterm = os.environ.get("TERM_PROGRAM") == "iTerm.app" or os.environ.get("LC_TERMINAL") == "iTerm2"
    return iterm and "TMUX" not in os.environ


def loop(scr, ed: Editor) -> None:
    try:
        edit_loop(scr, ed)
    finally:
        ed.flush_visits()  # leaving the pericope (quit, Open it, deleted): its visits so far
        if ed.drawn:
            scr.clearok(True)  # (whatever's drawn next repaints the screen, over the pictures)


def edit_loop(scr, ed: Editor) -> None:
    while True:
        ed.draw(scr)
        scr.refresh()
        ed.show_pictures()
        ready(scr, ed.dirty())
        wait = (RETRY_MS if ed.refused else AUTOSAVE_MS) if ed.dirty() else POLL_MS
        if ed.to_draw:  # (pictures waiting for the window to settle)
            wait = min(wait, SETTLE_MS)
        if ed.fetching():
            wait = min(wait, FETCH_MS)
        scr.timeout(wait)
        try:
            key = scr.get_wch()
            SEEN["keys"] += 1
        except curses.error:  # idle: autosave, then pick up changes saved elsewhere
            SEEN["wakes"] += 1
            if ed.dirty():
                ed.save()
            ed.refresh_library()
            ed.follow_store()
            ed.fetched()
            ed.visit_tick()
            continue
        # drain everything already waiting (a paste) before redrawing
        while key is not None:
            cur, before = ed.cur_id, list(ed.lines)
            done = ed.handle(scr, key)
            ed.visit_tick(key=True, wrote=ed.cur_id == cur and ed.lines != before)
            if done:
                return
            scr.timeout(0)
            try:
                key = scr.get_wch()
                SEEN["keys"] += 1
            except curses.error:
                key = None


def main(argv: list[str]) -> None:
    path, line, meta = None, 1, None
    args = iter(argv[1:])
    for arg in args:
        if arg == "--meta":
            meta = next(args, None)
        elif arg.startswith("+") and arg[1:].isdigit():
            line = int(arg[1:])
        elif path is None:
            path = arg
        else:
            sys.exit(f"fw_edit: unexpected argument '{arg}'")
    if path is None:
        sys.exit("usage: fw_edit.py FILE [+LINE] [--meta META.json]")

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("fw_edit: needs an interactive terminal")

    os.environ.setdefault("ESCDELAY", "25")
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(1))

    ed = Editor(path, line, meta)
    try:
        curses.wrapper(run, ed)
    except BaseException:
        if ed.dirty():
            ed.save()  # never lose writing
        raise


if __name__ == "__main__":
    main(sys.argv)
