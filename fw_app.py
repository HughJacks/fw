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
from datetime import datetime
import os
import signal
import sys

import fw_edit as edit
import fw_meaning
import fw_screen as screen
import fw_keys as keys
import fw_store as store
from fw_picker import NEW, PROPOSE, Garden, Picker, blocks_inside, new_label
from fw_state import Home, Review


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


def next_maybe(rv, attrs: screen.Ink, trail: list):
    """A review's next maybe (fw_state.Review: pericopes only), opened, its
    editor reviewing: (ref, draft, editor), or None when none is left. One
    that's gone or in no pericope is passed over (counted as skipped)."""
    while rv.queue and not rv.stop:
        bid, p = rv.queue[0]
        blocks = store.index(store.load_data())
        home, at = store.home_of(blocks, bid) if bid in blocks else (None, 0)
        try:
            if home is None:
                raise store.StoreError("gone")
            ref, tmp, _ = store.stage(home)
        except store.StoreError:
            rv.done.append((bid, p, None, None))
            rv.queue.pop(0)
            continue
        line, col = store.draft_place(Path(tmp).read_text(encoding="utf-8"), at)
        ed = editor(tmp, line + 1, attrs)  # at the block, as Open it does
        ed.cx = min(col, len(ed.lines[ed.cy]))
        ed.review = rv
        ed.trail = [e.library.get(r, {}).get("title", "untitled") for r, _, e in trail]
        return ref, tmp, ed
    return None


def write(scr, attrs: screen.Ink, target: tuple, forward: list | None = None) -> str:
    """Open `target` in the editor until it's quit; returns a note for home.
    target: ("new", title or None) | ("open", id) | ("title", title) | ("last", None)
    | ("propose", a proposal: the kind made, then its members reviewed).
    ("open", id) of a block inside an entry opens that entry, at the block.
    | ("forward", None): the last of `forward` ([(entry, draft offset)], what
    Ctrl+[ or ^Q went back from, the newest last), opened again where it was.
    Going back adds to `forward`; Ctrl+] in the editor steps into its last, as
    Open it does; anything opened anew (from home, or Open it) clears it."""
    forward = forward if forward is not None else []
    kind, arg = target
    review, again = None, None
    if kind == "forward":
        if not forward:
            return "nothing to go forward to"
        (arg, again), kind = forward.pop(), "open"
    else:
        forward.clear()  # opened anew: nothing ahead any more
    if kind == "propose":  # a kind a model proposes, taken: made, then its members to review, the kind waiting
        try:
            kid = store.kind_from_proposal(arg)
        except store.StoreError as e:
            return str(e)
        review = Review(kid, [(m, None) for m in arg["members"]], len(arg["members"]))
        kind, arg = "open", kid
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
        if again is not None and arg in blocks:
            at = again  # where it was left
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
    if review is not None:
        trail.append((ref, tmp, ed))
        nxt = next_maybe(review, attrs, trail)
        if nxt is None:
            trail.pop()
        else:
            ref, tmp, ed = nxt
    while True:
        try:
            edit.loop(scr, ed)
        except BaseException:
            if ed.dirty():
                ed.save()  # never lose writing
            for r, t, _ in trail:
                finish(r, t)  # saved before stepping in: this only tidies up
            raise
        if ed.deleted is not None or ed.gone:  # deleted, here or elsewhere: nothing to save; back, or home
            if ed.gone:
                note = f"'{ed.here_as}' was deleted elsewhere"
                if ed.dirty():  # (what was typed since the last save: kept, not lost)
                    Path(tmp).write_text(ed.draft(), encoding="utf-8")
                    note += f" · what you hadn't saved is in {tmp}"
                else:
                    store.drop_draft(tmp)
            else:
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
        ahead = ed.forward  # Ctrl+]: into the last place gone back from, as Open it steps in
        if ahead:
            ed.forward = False
            if not forward:
                ed.message = "nothing to go forward to"
                continue
            ed.opening = forward.pop()
        if ed.opening:
            if not ahead:
                forward.clear()  # opened anew: nothing ahead any more
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
        rv = ed.review
        if rv is not None and rv.kind == ref:  # a kind's maybes, to review: the kind waits on the trail
            ed.review = None
            trail.append((ref, tmp, ed))
            nxt = next_maybe(rv, attrs, trail)
            if nxt is None:
                ref, tmp, ed = trail.pop()
                ed.message = "none of them is still where it was"
                continue
            ref, tmp, ed = nxt
            continue
        if rv is not None:  # a maybe answered (or skipped, or back, or stop): the next, else back to the kind
            finish(ref, tmp)
            nxt = next_maybe(rv, attrs, trail)
            if nxt is not None:
                ref, tmp, ed = nxt
                continue
            left = ref
            ref, tmp, ed = trail.pop()
            ed.refresh_library()
            ed.follow_store()
            ed.came_back(left)
            ed.reviewed(rv)
            ed.visit_open()
            continue
        where = ed.where()
        note = finish(ref, tmp)
        if ref in store.index(store.load_data()):  # (not discarded, left empty): Ctrl+] comes back to it
            forward.append((ref, where))
        if not trail:
            return note
        left = ref
        ref, tmp, ed = trail.pop()  # ^Q steps back, to where Open it was
        ed.refresh_library()
        ed.follow_store()
        ed.message, ed.stale = note, True
        ed.came_back(left)
        ed.visit_open()


def home(scr, message: str, attrs: screen.Ink = screen.Ink(), spot: Home | None = None):
    """The home screen; returns the next target, ("home", note) after a
    delete there (home again), or None to quit. `spot` (fw_state.Home): as
    it was left, kept as it's left again (the view, what was typed, the
    selection: the same place after a delete, or coming back)."""
    spot = spot if spot is not None else Home()
    library = store.build_library(store.load_data())
    refs = sorted((r for r, e in library.items() if e["entry"]), reverse=True)  # newest first
    guesses = store.load_guesses()
    offer = next(iter(store.open_proposals(store.load_proposals(), library, store.load_dismissed(),
                                           store.kind_cover(library, guesses))), None)  # one at a time
    pinned = [(NEW, new_label)] + ([(PROPOSE, lambda q: f"? a kind: {offer['name']} · {len(offer['members'])} alike", True)]
                                   if offer else [])
    picker = Picker(library, refs, pinned=pinned, inside=blocks_inside(library, refs),
                    guesses=store.guessed(guesses, library), applied=store.learned(guesses))
    picker.blue = attrs.blue
    picker.sel = len(pinned) if refs else 0  # the newest entry: usually the one just closed
    def footer(k):
        if k == NEW:
            return ""
        if k == PROPOSE:
            return "↵ make it a kind, then say which of them are · ^D dismiss it"
        if store.quoted(library.get(k)):
            return "↵ open it there, at the quote"
        if not library[k]["entry"]:
            return "↵ open it where it lives · ← hide"
        return "↵ open it" + (" · ← hide its blocks" if k in picker.shown else
                              " · → its blocks" if picker.inside.get(k) else "")
    picker.footer = footer
    garden = home_garden(library, refs, pinned, offer)
    garden.kinds, garden.blue, garden.grid = picker.kinds, attrs.blue, spot.grid
    view = garden  # home starts as the garden; typing hands over to the search
    if spot.sel is not None and garden.cards:
        garden.sel = min(spot.sel, len(garden.cards) - 1)
    if spot.search:
        view, picker.query = picker, spot.query
        rows = len(picker.rows())
        picker.sel = min(spot.picked, rows - 1) if spot.picked is not None and rows else picker.first_result()
        picker.moved = True
    def left(target):
        """`target`, home kept as it is (spot) for coming back."""
        spot.search, spot.query, spot.grid = view is picker, picker.query if view is picker else "", garden.grid
        spot.sel, spot.picked = garden.sel, picker.sel if view is picker else None
        return target
    prev_cr = False
    seen = store_stamp()
    asker = fw_meaning.Asker()  # (the search service, asked what's near what's typed: mixed into the search)
    while True:
        draw_home(scr, view, len(refs), message)
        screen.ready(scr)
        scr.timeout(edit.POLL_MS)  # (and looks at the store as the editor does: written elsewhere, home is redrawn)
        try:
            key = scr.get_wch()
            screen.SEEN["keys"] += 1
        except curses.error:
            screen.SEEN["wakes"] += 1
            if store_stamp() != seen:  # another session or machine wrote it: home again, as it was left
                return left(("home", message))
            if view is picker:
                asker.want(picker.query)
                got = asker.tick()
                if got:
                    picker.meaning = got
                    if not picker.moved:
                        picker.sel = picker.first_result()
            continue
        act = keys.bind(keys.decode(scr, key, prev_cr), "picker")
        prev_cr = key == "\r"
        if act == "delete_entry":
            row = ((garden.selected(),) if view is garden and garden.selected() else
                   picker.rows()[picker.sel] if view is picker and picker.rows() else None)
            if row and row[0] == PROPOSE:
                return left(("home", ask_dismiss(scr, view, len(refs), offer)))
            if row and row[0] in refs:  # (a pericope: not a block inside one)
                return left(("home", ask_delete(scr, view, len(refs), row[0], library)))
            message = "^D deletes a pericope; this is a block inside one" if row and row[0] != NEW else message
            continue
        if act in ("quit", "mouse") or key == curses.KEY_RESIZE:
            if act == "quit":
                return None
            continue
        if act == "go_forward":
            if spot.forward:
                return left(("forward", None))
            message = "nothing to go forward to"
            continue
        if view is garden:
            done = garden.key(act)
            if isinstance(done, tuple) and done[0] == "search":
                view, picker.query = picker, done[1]
                picker.sel, picker.moved = picker.first_result(), False
                done = None
        else:
            done = picker.key(act)
            if done == "back":  # Backspace with nothing typed: the garden again
                view, done = garden, None
        message = ""
        if done == "cancel":
            return None
        if isinstance(done, tuple):
            if done[1] == PROPOSE:
                return left(("propose", offer))
            typed = picker.query if view is picker else ""
            return left(("new", typed or None) if done[1] == NEW else ("open", done[1]))


def store_stamp():
    """When the store was last written (None if there's none)."""
    try:
        return store.DATA_PATH.stat().st_mtime_ns
    except OSError:
        return None


def home_garden(library: dict, refs: list, pinned: list, offer: dict | None = None) -> Garden:
    """The garden over the entries: fw_block.garden's order, a card's text
    from the library, as of now; a proposed kind (`offer`) a dim card after
    "+ new pericope", saying what Enter and ^D do (the garden has no footer)."""
    blocks = {i: e["block"] for i, e in library.items()}
    now = int(store.clock() // 60)
    def info(i):
        b = blocks[i]
        made = store.iso_minute(b.get("created"))
        changed = store.iso_minute(b.get("updated"))
        mmdd = lambda m: datetime.fromtimestamp(m * 60).strftime("%b %-d") if m is not None else "?"
        dates = f"made {mmdd(made)}" + (f" · changed {mmdd(changed)}" if changed and made and changed - made > 1 else "")
        what, when = store.last_action(b)
        return library[i]["title"], dates, f"{what} {store.ago(when, now)}".strip(), store.full_text(blocks, i)
    cards = [(k, f"a kind: {offer['name']}" if k == PROPOSE else label("")) for k, label, *_ in pinned]
    notes = {PROPOSE: [f"{len(offer['members'])} pericopes alike, no kind yet", "↵ make it a kind, then say",
                       "  which of them are one", "^D dismiss it"]} if offer else {}
    right = lambda i: f"{i[4:6]}/{i[6:8]}  {library[i].get('words', 0)}w"  # (as the search's rows)
    g = Garden(store.garden(blocks, refs, now), info, pinned=cards, notes=notes, faint={PROPOSE}, right=right)
    if offer:
        g.why[PROPOSE] = "proposed"
    return g


def ask_dismiss(scr, picker, count: int, offer: dict) -> str:
    """Home: the proposed kind `offer` dismissed, once asked (y): never offered again."""
    draw_home(scr, picker, count, f"dismiss the kind '{offer['name']}'? y dismisses it for good · any other key keeps it")
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
        store.dismiss_proposal(offer)
    except OSError as e:
        return str(e)
    return f"dismissed the kind '{offer['name']}'"


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
    hint = (f"⏎ open  ←↑↓→ move  type to search  ^G {'list' if picker.grid else 'grid'}  ^D delete  esc quit "
            if isinstance(picker, Garden)
            else "⏎ open  ↑↓ move  ⌫ garden  ^D delete  esc quit ")
    bar = left + " " * max(w - len(left) - len(hint), 1) + (hint if len(left) + len(hint) < w else "")
    screen.put(scr, h - 1, 0, bar[:w - 1].ljust(w - 1), curses.A_REVERSE)
    try:
        scr.move(y, min(x, w - 1))
    except curses.error:
        pass


def app(scr, target) -> None:
    attrs = screen.setup(scr)
    with screen.keyboard_modes():
        message, spot = "", Home()  # (home as it was left, and the places gone back from)
        while True:
            while target is None or target[0] == "home":  # home, again after a delete there
                target = home(scr, target[1] if target else message, attrs, spot)
                if target is None:
                    return
            message, target = write(scr, attrs, target, spot.forward), None


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
    try:
        main(sys.argv)
    except store.StoreError as e:  # (a store fw can't read: said, and stopped, as load_data used to)
        store.die(str(e))
