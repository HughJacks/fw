#!/usr/bin/env python3
"""fw_app — fw as one app: write, then pick what's next from home.

    fw_app.py [--new [TITLE] | --title TITLE | --last | --home]

Opens the first entry in the editor (a new one by default; --title opens the
entry with that title, or starts it; --last the newest; --home starts at
home). Quitting the editor (^Q) goes home: a search list of every entry,
the same one the quote search uses (typing filters by title, and finds the
blocks inside entries too, each match with its paraphrase family and, below,
the places that quote it). Enter opens an entry, or the entry a block lives
in, at that block; "+ new pericope" starts one (titled with what you typed);
Esc quits. (The UI calls an entry a pericope.)

The loop is: stage an entry (fw_store.stage), edit it (fw_edit), finish it
(fw_store.finish), go home. If finishing fails, the draft is kept and home
says where. Open it (on a quote) steps into the quote's source: the editor
stepped out of waits on a trail, undo and all, and ^Q steps back to it.
"""

from pathlib import Path

import curses
import os
import signal
import sys

import fw_edit as edit
import fw_screen as screen
import fw_keys as keys
import fw_store as store
from fw_picker import NEW, Picker, blocks_inside, new_label


def editor(tmp: str, line: int, attrs: screen.Ink) -> edit.Editor:
    ed = edit.Editor(tmp, line, str(store.meta_path(tmp)))
    ed.ink = attrs
    return ed


def finish(ref: str, tmp: str) -> str:
    """The last save of `ref`'s session; returns a note saying how it went."""
    try:
        notes = store.finish(ref, tmp)
    except store.StoreError as e:
        return f"{e} — your writing is safe in {tmp}"
    store.drop_draft(tmp)
    title = store.build_library(store.load_data()).get(ref, {}).get("title")
    return notes[-1] if notes else f"saved · {title}" if title else ""


def write(scr, attrs: screen.Ink, target: tuple) -> str:
    """Open `target` in the editor until it's quit; returns a note for home.
    target: ("new", title or None) | ("open", id) | ("title", title) | ("last", None).
    ("open", id) of a block inside an entry opens that entry, at the block."""
    kind, arg = target
    if kind in ("title", "last"):
        ref = store.find_entry(store.load_data(), title=arg, last=kind == "last")
        kind, arg = ("open", ref) if ref else ("new", arg)
    at = None
    if kind == "open":
        blocks = store.index(store.load_data())
        if arg in blocks and not blocks[arg].get("entry"):  # a block inside an entry: that entry, at it
            arg, at = store.home_of(blocks, arg)
            if arg is None:
                return "it's in no pericope"
    try:
        ref, tmp, line = store.stage(arg if kind == "open" else None, arg if kind == "new" else None,
                                     append=kind == "open" and at is None)
    except store.StoreError as e:
        return str(e)
    if at is not None:
        line, col = store.draft_place(Path(tmp).read_text(encoding="utf-8"), at)
        ed = editor(tmp, line + 1, attrs)  # as Open it does
        ed.cx = min(col, len(ed.lines[ed.cy]))
    else:
        ed = editor(tmp, line, attrs)
    if kind == "open" and at is None:
        ed.cx = len(ed.lines[ed.cy])  # at the end of what's there
    trail = []  # (ref, draft, editor) of each entry stepped in from, outermost first
    while True:
        try:
            edit.loop(scr, ed)
        except BaseException:
            if ed.dirty():
                ed.save()  # never lose writing
            for r, t, _ in trail:
                finish(r, t)  # saved before stepping in: this only tidies up
            raise
        if ed.deleted is not None:  # deleted from inside: nothing to save; back, or home
            title = ed.library.get(ref, {}).get("title", "")
            store.drop_draft(tmp)
            note = f"deleted '{title}'" + (f" · {ed.deleted} quote{'s' * (ed.deleted != 1)} of it now plain text"
                                           if ed.deleted else "")
            if not trail:
                return note
            gone = ref
            ref, tmp, ed = trail.pop()
            ed.refresh_library()
            ed.follow_store()
            ed.message, ed.stale = note, True
            ed.came_back(gone)
            ed.visit_open()
            continue
        if ed.opening:
            src, at = ed.opening
            ed.opening = None
            try:
                src, stmp, _ = store.stage(src)
            except store.StoreError as e:
                ed.message = str(e)
                continue
            trail.append((ref, tmp, ed))
            ref, tmp = src, stmp
            line, col = store.draft_place(Path(tmp).read_text(encoding="utf-8"), at) if at is not None else (0, 0)
            ed = editor(tmp, line + 1, attrs)  # at the start, a masked quote's first shown part, or the cursor
            ed.cx = min(col, len(ed.lines[ed.cy]))
            ed.trail = [e.library.get(r, {}).get("title", "untitled") for r, _, e in trail]
            continue
        note = finish(ref, tmp)
        if not trail:
            return note
        left = ref
        ref, tmp, ed = trail.pop()  # ^Q steps back, to where Open it was
        ed.refresh_library()
        ed.follow_store()
        ed.message, ed.stale = note, True
        ed.came_back(left)
        ed.visit_open()


def home(scr, message: str):
    """The home screen; returns the next target, ("home", note) after a
    delete there (home again), or None to quit."""
    library = store.build_library(store.load_data())
    refs = sorted((r for r, e in library.items() if e["entry"]), reverse=True)  # newest first
    picker = Picker(library, refs, pinned=[(NEW, new_label)], inside=blocks_inside(library, refs))
    picker.sel = 1 if refs else 0  # the newest entry: usually the one just closed
    def footer(k):
        if k == NEW:
            return ""
        if store.quoted(library.get(k)):
            return "↵ open it there, at the quote"
        if not library[k]["entry"]:
            return "↵ open it where it lives · ← hide"
        return "↵ open it" + (" · ← hide its blocks" if k in picker.shown else
                              " · → its blocks" if picker.inside.get(k) else "")
    picker.footer = footer
    prev_cr = False
    while True:
        draw_home(scr, picker, len(refs), message)
        screen.ready(scr)
        scr.timeout(-1)
        try:
            key = scr.get_wch()
            screen.SEEN["keys"] += 1
        except curses.error:
            screen.SEEN["wakes"] += 1
            continue
        act = keys.bind(keys.decode(scr, key, prev_cr), "picker")
        prev_cr = key == "\r"
        if act == "delete_entry":
            row = picker.rows()[picker.sel] if picker.rows() else None
            if row and row[0] in refs:  # (a pericope: not a block inside one)
                return ("home", ask_delete(scr, picker, len(refs), row[0], library))
            message = "^D deletes a pericope; this is a block inside one" if row and row[0] != NEW else message
            continue
        if act in ("quit", "mouse") or key == curses.KEY_RESIZE:
            if act == "quit":
                return None
            continue
        done = picker.key(act)
        message = ""
        if done == "cancel":
            return None
        if isinstance(done, tuple):
            return ("new", picker.query or None) if done[1] == NEW else ("open", done[1])


def ask_delete(scr, picker, count: int, ref: str, library: dict) -> str:
    """Home: delete entry `ref` (a pericope), once asked (y). Returns a note for home."""
    title = library[ref]["title"]
    draw_home(scr, picker, count, f"delete '{title}'? y deletes it for good · any other key keeps it")
    screen.ready(scr)
    scr.timeout(-1)
    try:
        key = scr.get_wch()
        screen.SEEN["keys"] += 1
    except curses.error:
        return "kept"
    if key != "y":
        return "kept"
    try:
        kept = store.delete_entry(ref)
    except store.StoreError as e:
        return str(e)
    return f"deleted '{title}'" + (f" · {kept} quote{'s' * (kept != 1)} of it now plain text" if kept else "")


def draw_home(scr, picker, count: int, message: str) -> None:
    h, w = scr.getmaxyx()
    scr.erase()
    screen.put(scr, 0, 1, f"fw  ·  {count} pericope{'' if count == 1 else 's'}"[:w - 2], curses.A_DIM)
    max_rows = max(h - 6, 1)
    y, x = picker.draw(scr, 1, 1, max(w - 2, 20), max_rows, "open › ")
    left = f" fw  {message}" if message else " fw"
    hint = "⏎ open  ↑↓ move  ^D delete  esc quit "
    bar = left + " " * max(w - len(left) - len(hint), 1) + (hint if len(left) + len(hint) < w else "")
    screen.put(scr, h - 1, 0, bar[:w - 1].ljust(w - 1), curses.A_REVERSE)
    try:
        scr.move(y, min(x, w - 1))
    except curses.error:
        pass


def app(scr, target) -> None:
    attrs = screen.setup(scr)
    with screen.keyboard_modes():
        message = ""
        while True:
            while target is None or target[0] == "home":  # home, again after a delete there
                target = home(scr, target[1] if target else message)
                if target is None:
                    return
            message, target = write(scr, attrs, target), None


def main(argv: list[str]) -> None:
    args, target = argv[1:], ("new", None)
    if args[:1] == ["--new"]:
        target = ("new", args[1] if len(args) > 1 else None)
    elif args[:1] == ["--title"] and len(args) == 2:
        target = ("title", args[1])
    elif args == ["--last"]:
        target = ("last", None)
    elif args == ["--home"]:
        target = None
    elif args:
        sys.exit("usage: fw_app.py [--new [TITLE] | --title TITLE | --last | --home]")
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.exit("fw_app: needs an interactive terminal")
    os.environ.setdefault("ESCDELAY", "25")
    for sig in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(1))
    curses.wrapper(app, target)


if __name__ == "__main__":
    main(sys.argv)
