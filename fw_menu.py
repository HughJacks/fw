"""fw_menu — the editor's / menu and the commands it runs, part of the editor
(a mixin of fw_edit.Editor, whose state it works on). Adding a command: list
it in `commands` as a Command, name its method in `run_command`, write the
method here. Two choices for each:

- group: nest it in a submenu (a Command whose name is "group:<name>" opens
  it). The top level shows only the submenu's entry, but a search finds the
  commands inside it too, so they never hide from typing.
- stays: whether the menu stays open after it runs. A command that's done
  once closes it (Open it, Turn into text); one you'd do a few of in a row
  stays (toggles, like what a quote's top line shows), its label refreshed.

A row shows the command's name and, on the right, its key if KEYMAP binds
one to its method (RUNS); the note, what it does, shows dim at the bottom
for the command selected. The name should say what it does. A command's key
runs it only where the menu would offer it (command_key).
"""

import threading
from typing import NamedTuple

import fw_store as store
import fw_keys as keys
from fw_picker import NEW, Picker, blocks_inside, new_kind_label, new_label
from fw_screen import draw_box, swidth
from fw_state import Menu
from fw_store import atom_id, is_atom, quote_line

PALETTE_ROWS = 8


class Command(NamedTuple):
    name: str
    label: str
    note: str               # what it does, dim at the bottom while it's selected
    group: str | None = None  # the submenu it's in (None: the top level)
    stays: bool = False     # the menu stays open after it
# the method each command runs (also the action a key in KEYMAP would bind to run it)
RUNS = {"mask": "edit_mask", "showall": "show_all", "open": "open_source",
        "detach": "detach", "popout": "pop_out", "popopen": "pop_out_open",
        "link": "link_entry", "unlink": "remove_link",
        "paraphrase": "paraphrase_of", "unparaphrase": "not_paraphrase", "paraphrase_it": "paraphrase_it",
        "lock": "toggle_lock"}
# what a lock refuses (fw_block.locked_by): commands that write in the block you're in, and those that
# change the quote's own properties (refused only when that quote is itself inside a lock)
WRITE_CMDS = {"quote", "image", "detach", "popout", "popopen", "link", "unlink",
              "paraphrase_it", "paraphrase", "unparaphrase"}
OWN_CMDS = {"mask", "showall", "group:topline", "lock"}


def shortcut(cmd: Command) -> str:
    """The key that runs `cmd` in the text, if one does."""
    bound = keys.keys_of(RUNS.get(cmd.name), "text")
    return bound[0] if bound else ""
SHOW_NAMES = {"title": "title", "created": "date", "updated": "last update", "words": "word count"}


class Commands:
    # --- the / menu ---------------------------------------------------
    def quote_refs(self) -> list:
        """Entries that can be quoted here, newest first (ids sort by creation)."""
        return sorted((ref for ref, e in self.library.items() if e["entry"] and ref not in self.open_ids()),
                      reverse=True)

    def quote_inside(self, refs: list) -> dict:
        """The blocks inside each of `refs` that can be quoted (not quotes), in
        order, with how deep: {entry: [(block, depth), …]}."""
        return blocks_inside(self.library, refs)

    def open_quote_search(self) -> None:
        """The second stage of the / menu: pick the block to quote, an entry
        or a block inside one (those whose title has what you type, under
        their entry), or + new entry (titled with what you typed) to write a
        new one, quoted here."""
        refs = self.quote_refs()
        picker = Picker(self.library, refs, pinned=[(NEW, new_label)] if self.self_id else [],
                        inside=self.quote_inside(refs), guesses=self.guesses(),
                        applied=store.learned(store.load_guesses()))
        picker.blue = self.ink.blue
        picker.sel = picker.first_result()
        def footer(k):
            if store.quoted(self.library.get(k)):
                return "↵ quote what it quotes"
            if k in self.library and not self.library[k]["entry"]:
                return "↵ its own pericope · ⇧↵ its pericope, masked to it · ← hide"
            more = (" · ← hide its blocks" if k in picker.shown else
                    " · → its blocks" if picker.inside.get(k) else "")
            return "↵ quote it" + more
        picker.footer = footer
        self.palette = Menu("block", picker=picker)

    def commands(self, slash: bool = False, every: bool = False) -> list:
        """The menu's commands that fit where the cursor is, as Commands: the
        / menu's put a block in here (inserts), Ctrl+/'s act on the block
        you're in (actions); none is in both. Those a lock refuses here are
        left out (`every`: kept)."""
        line = self.lines[self.cy]
        q = self.quote_at(line)
        if slash:
            return [c for c in self.inserts(line) if every or not self.lock_refuses(c)]
        cmds = []
        if self.stack or (q and self.enterable(self.cy)):
            here = q[1] if q else self.quote_at(self.stack[-1].lines[self.stack[-1].anchor])[1]
            masked = self.masked(here)
            cmds.append(Command("mask", "Edit mask" if masked else "Create mask",
                                "choose what it shows, with [ ]"))
        here = self.quote_here()
        if here and self.masked(here[1]):
            cmds.append(Command("showall", "Remove mask", "show all of it again"))
        link = None if q else self.link_here()
        if link:
            cmds.append(Command("open", "Open it", "the pericope it links to"))
        elif q:
            cmds.append(Command("open", "Open it", "its source, as the pericope you're in"))
        elif self.stack:
            cmds.append(Command("open", "Open it", "the quote you're in, as the pericope, here"))
        para = None if q else self.para_here()
        if para and not link and not self.stack:
            cmds.append(Command("open", "Open it", "the block it paraphrases"))
        if para:
            cmds.append(Command("peek", "Hide its source" if para[0] in self.peeking else "Show its source",
                                "its source's text, dim, inside it", stays=True))
        shows = self.quote_here()
        if shows:
            cmds.append(Command("group:topline", "Its top line…", "show its title, date, …"))
            for k in store.SHOWABLE:
                on = k in self.show_of(shows[1])
                cmds.append(Command(f"show:{k}", f"{'Hide' if on else 'Show'} its {SHOW_NAMES[k]}",
                                    "in its top line", group="topline", stays=True))
            if store.quote_lock(self.library.get(shows[1])):
                cmds.append(Command("lock", "Unlock writing through", "what it shows can be changed here again",
                                    stays=True))
            else:
                cmds.append(Command("lock", "Lock writing through", "what it shows can't be changed from here",
                                    stays=True))
        if q:
            cmds.append(Command("detach", "Turn into text", "a plain copy, no longer live"))
        elif (line.strip() or self.selection()) and self.self_id and not self.vmode:
            cmds.append(Command("popout", "Turn into a quote", "the selection to a pericope of its own, nested here"
                                if self.selection() else "this block to a pericope of its own"))
            cmds.append(Command("popopen", "Turn into a quote and open it", "…and step into it"))
        if self.selection() and self.self_id and not self.vmode and self.selected_span():
            cmds.append(Command("link", "Link to a pericope", "the selection points to a pericope"))
        if link:
            cmds.append(Command("unlink", "Remove link", "the text stays as it is"))
        mine = self.mark_target()
        if (q and self.self_id and not self.vmode) or (mine and not store.paraphrases(self.library.get(mine))):
            cmds.append(Command("paraphrase_it", "Paraphrase it", "your words in its place"
                                if q else "it moves out; your words in its place"))
        if mine and not store.paraphrases(self.library.get(mine)):
            cmds.append(Command("paraphrase", "Paraphrases…", "mark this block as a paraphrase of another"))
        if para:
            cmds.append(Command("unparaphrase", "Not a paraphrase", "your words stay, no longer pointing"))
        return [c for c in cmds if every or not self.lock_refuses(c)]

    def lock_refuses(self, cmd: Command) -> bool:
        """Whether a locked quote keeps `cmd` from running here: it writes in
        the block you're in, through a lock; or it changes the quote's own
        properties, and that quote is itself inside a lock."""
        if cmd.name in OWN_CMDS or cmd.name.startswith("show:"):
            return self.quote_locked()
        return cmd.name in WRITE_CMDS and self.locked()

    def mark_target(self) -> str | None:
        """The block a paraphrase mark would go on, at the cursor: its block of
        text, or the picture it's on (not a quote; not in a masked view)."""
        if not self.self_id or self.vmode or self.selection():
            return None
        line = self.lines[self.cy]
        if self.quote_at(line) or not (is_atom(line) or line.strip()):
            return None  # (a quote, or an empty line: nothing written to mark)
        return atom_id(line) if is_atom(line) else self.bids[self.cy]

    def para_here(self):
        """The paraphrase the cursor's in, innermost first (its block, or a
        container it's in): (that block, its source), else None."""
        if self.vmode:
            return None
        line = self.lines[self.cy]
        own = atom_id(line) if is_atom(line) else self.bids[self.cy]
        for ref in [own, *reversed(self.containers(self.cy))]:
            source = store.paraphrases(self.library.get(ref))
            if source:
                return ref, source
        return None

    def paraphrase_of(self) -> None:
        """Paraphrases…: pick the block this one paraphrases (an entry, or a
        block inside one), in the quote search."""
        if self.dirty():
            self.save()
        self.refresh_library()
        target = self.mark_target()
        if target not in self.library:
            self.message = "write something first"
            return
        refs = self.quote_refs()
        self.palette = Menu("paraphrase", picker=Picker(self.library, refs, inside=self.quote_inside(refs)),
                            mark=target)

    def paraphrase_it(self) -> None:
        """Paraphrase it: on a quote, an empty paraphrase of what it quotes
        takes its place; on a block you wrote (or a picture), the block moves
        to an entry of its own (as Turn into a quote) and an empty paraphrase
        of that takes its place. The source shows dim inside it until you
        write. One undo takes it all back."""
        if self.dirty():
            self.save()
        self.refresh_library()
        line = self.lines[self.cy]
        q = self.quote_at(line)
        record = None
        if q:
            source, gone = q[0], (self.cy, self.cy)
        else:
            ref = self.mark_target()
            if ref not in self.library:
                self.message = "write something first"
                return
            try:
                source, h, record = store.pop_out(ref)
                self.base.update(h)
            except store.StoreError as e:
                self.message = str(e)
                return
            gone = (self.cy, self.cy) if is_atom(line) else self.block_at(self.cy)
        outer = self.outer(gone[0])
        try:
            pid, undo = store.new_paraphrase(source, record)
        except store.StoreError as e:
            if record:
                store.restore(record)
            self.message = str(e)
            return
        self.step(undo)
        self.lines[gone[0]:gone[1] + 1] = [""]
        self.bids[gone[0]:gone[1] + 1] = [pid]
        if outer:
            self.nest[pid] = outer
        self.cy, self.cx, self.unit_side, self.anchor = gone[0], 0, None, None
        self.refresh_library()
        self.save()
        self.message = "write it in your own words"

    def set_mark(self, ref: str, source: str | None) -> None:
        """Mark block `ref` a paraphrase of `source` (None: not one), one undo step."""
        try:
            record = store.set_paraphrase(ref, source)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        self.stale = True
        self.message = "a paraphrase now" if source else "not a paraphrase now: your words stay"

    def not_paraphrase(self) -> None:
        """Not a paraphrase: the mark goes, the words stay."""
        para = self.para_here()
        if para:
            self.set_mark(para[0], None)

    def inserts(self, line: str) -> list:
        """The / menu: blocks to put in at the cursor (room_here: in a
        block's text they nest there, splitting it). In a masked view, only
        on an empty line."""
        if self.is_atom(self.cy) or (self.vmode and line.strip()):
            return []
        cmds = [Command("quote", "Quote a block", "show another block here")]
        if self.self_id and not self.vmode:
            cmds.append(Command("image", "Add a picture from a link", "downloaded into fw, kept here"))
        return cmds

    def command_key(self, act: str) -> None:
        """A command's key (its method's name, as KEYMAP binds it): run it if
        the menu would offer it here. Deleting the entry is the window's, not
        a block's: it's no menu command, only a key."""
        if act == "delete_entry":
            if self.self_id and not self.medit:
                self.ask_delete()
            return
        offered = [] if self.medit else [c for c in self.commands(every=True) if RUNS.get(c.name) == act]
        if offered and self.lock_refuses(offered[0]):
            self.message = "locked"
        elif offered:
            getattr(self, act)()
        else:
            self.message = "not here"

    def masked(self, qid) -> bool:
        """Whether quote block `qid` has a mask: its own, or for a quote inside it."""
        b = self.library.get(qid)
        return bool(store.quoted(b)) and (store.quoted(b)[1] is not None or bool(store.quote_inner(b)))

    def menu_items(self) -> list:
        """What the open menu lists: the commands of the submenu it's in (the
        top level: those in none), or, while searching the top level, every
        command that matches, nested or not."""
        p = self.palette
        query = p.query.lower()
        if query and p.group is None:
            return [c for c in p.commands if query in c.label.lower()]
        return [c for c in p.commands if c.group == p.group and query in c.label.lower()]

    def open_menu(self, typed_slash: bool) -> None:
        cmds = self.commands(typed_slash)
        if not cmds:
            self.message = "nothing to do here"
            return
        self.palette = Menu("command", commands=cmds, slash=typed_slash)

    def run_command(self, cmd: Command) -> None:
        p = self.palette
        if cmd.name.startswith("group:"):
            p.group, p.query, p.sel = cmd.name[6:], "", 0
            return
        if cmd.name == "quote":
            self.open_quote_search()
            return
        if cmd.name == "image":
            self.palette = Menu("url")
            return
        if not cmd.stays:
            self.palette = None
        if cmd.name == "peek":
            para = self.para_here()
            if para:
                self.peeking ^= {para[0]}
                self.stale = True
        elif cmd.name.startswith("show:"):
            self.toggle_show(cmd.name[5:])
        else:
            getattr(self, RUNS[cmd.name])()
        if cmd.stays:  # still open: the labels as they are now
            p.commands, p.used = self.commands(p.slash), True
            p.sel = min(p.sel, max(len(self.menu_items()) - 1, 0))

    def palette_key(self, act: str | None) -> None:
        p = self.palette
        if p.stage == "url":
            self.url_key(act)
            return
        if p.picker is not None:
            done = p.picker.key(act)
            if done == "back" and p.stage == "kinds":
                self.palette = None
            elif done == "back":
                self.open_menu(True)
            elif done == "cancel":
                self.palette = None
            elif done and p.stage == "paraphrase":
                self.palette = None
                if done[1] != NEW:
                    self.set_mark(p.mark, p.picker.source(done[1]))
            elif done and p.stage == "kinds":
                if done[1] == NEW and not p.picker.query.strip():
                    self.message = "type the new kind's name first"
                    return
                self.palette = None
                self.answer_kind(None if done[1] == NEW else done[1], done[0] == "pick", p.picker.query)
            elif done and p.stage == "backlinks":
                self.palette = None
                self.follow_backlink(p.found[int(done[1])])
            elif done and p.stage == "link":
                self.palette = None
                self.link_to(p.span, None if done[1] == NEW else done[1], p.picker.query)
            elif done:
                self.palette = None
                done = (done[0], p.picker.source(done[1]))  # (a place quoting a match: quote the match)
                home = p.picker.home(done[1])
                if done[1] == NEW:
                    self.quote_new(p.picker.query)
                elif home is None:
                    self.insert_quote(done[1])
                elif done[0] == "masked":
                    self.quote_masked(home, done[1])
                else:
                    self.quote_promoted(done[1])
            return
        items = self.menu_items()
        if act == "cancel":
            self.palette = None
            if not p.used:
                for ch in ("/" if p.slash else "") + p.query:  # dismissing keeps what you typed, as text
                    self.insert(ch)
        elif act == "backspace":
            if p.query:
                p.query = p.query[:-1]
                p.sel = 0
            elif p.group is not None:
                p.group, p.sel = None, 0  # out of the submenu, back to the top
            else:
                self.palette = None  # deleting the "/" closes the menu
        elif act in ("up", "down"):
            p.sel = min(max(p.sel + (1 if act == "down" else -1), 0), max(len(items) - 1, 0))
        elif act == "pick":
            if items:
                self.run_command(items[p.sel])
        elif act is not None and len(act) == 1:
            p.query += act
            p.sel = 0
            if p.slash and p.group is None and not self.menu_items():
                self.palette = None  # nothing it could be: it was writing (a "/ " or "/usr"), typed in
                for ch in "/" + p.query:
                    self.insert(ch)

    def url_key(self, act: str | None) -> None:
        """Add a picture from a link: type (or paste) its web address; Enter
        downloads it, in the background (the editor checks on it, fetched),
        and Esc stops waiting. Backspace with nothing typed goes back to the menu."""
        p = self.palette
        if act == "cancel":
            self.palette = None
            return
        if p.fetch is not None:
            return  # (downloading: only Esc)
        p.note = ""
        if act == "backspace":
            if p.query:
                p.query = p.query[:-1]
            else:
                self.open_menu(True)
        elif act == "pick" and p.query.strip():
            fetch = p.fetch = {"result": None}
            def get(url=p.query.strip()):
                try:
                    fetch["result"] = (True, store.fetch_image(url))
                except store.StoreError as e:
                    fetch["result"] = (False, str(e))
            threading.Thread(target=get, daemon=True).start()
        elif act is not None and len(act) == 1:
            p.query += act

    def draw_palette(self, scr, h: int, w: int, cur_y: int, cur_x: int) -> tuple[int, int]:
        """Draw the / menu at the cursor: just below it (above, if there's no
        room), its left edge under the cursor (moved left only as far as it
        must to fit). Returns where the cursor goes."""
        p = self.palette
        bw = max(min(58, w - 1), 20)
        x0 = max(min(cur_x, w - 1 - bw), 0)
        if p.stage == "url":
            prompt = "picture › " + p.query
            if swidth(prompt) > bw - 4:  # (a long one: its end, where you're typing)
                prompt = "picture › …" + p.query[-(bw - 16):]
            row = ("downloading…" if p.fetch else p.note) or "a link to a png, jpeg, gif or webp"
            y0 = cur_y + 1 if cur_y + 5 <= h - 1 else max(cur_y - 5, 0)
            return draw_box(scr, y0, x0, bw, prompt, "", [("", row, "")], -1, 0,
                            "Esc stops waiting" if p.fetch else "Enter downloads it, kept here")
        if p.picker is not None:
            picker = p.picker
            bh = picker.height(PALETTE_ROWS)
            y0 = cur_y + 1 if cur_y + 1 + bh <= h - 1 else max(cur_y - bh, 0)
            prompt = {"link": "link › ", "backlinks": "backlinks › ", "paraphrase": "paraphrases › ",
                      "kinds": "kinds › "}.get(p.stage, "quote › ")
            return picker.draw(scr, y0, x0, bw, PALETTE_ROWS, prompt)
        items = self.menu_items()
        rows = [(c.name, c.label, shortcut(c)) for c in items]
        footer = items[p.sel].note if items else ""
        bh = len(rows or [None]) + 3 + bool(footer)
        y0 = cur_y + 1 if cur_y + 1 + bh <= h - 1 else max(cur_y - bh, 0)
        where = next((c.label.rstrip("…") + " › " for c in p.commands if c.name == f"group:{p.group}"), "")
        prompt = ("/" if p.slash else "⌃/ ") + where + p.query
        # only as wide as what it lists (the full list, so it doesn't jump as you type)
        need = max([swidth(c.label) + 2 + swidth(shortcut(c)) for c in p.commands]
                   + [swidth(c.note) for c in p.commands] + [swidth(prompt) + 4]) + 4
        bw = max(min(need, 58, w - 1), 20)
        x0 = max(min(cur_x, w - 1 - bw), 0)
        return draw_box(scr, y0, x0, bw, prompt, "", rows, p.sel, 0, footer)

    # --- turn into ------------------------------------------------------
    def open_source(self) -> None:
        """Step into the quote at the cursor, or the one it's editing in (at
        the cursor): fw_app opens its source as the entry, keeping this editor
        on the trail, and ^Q there comes back here."""
        if self.dirty():
            self.save()
        q = self.quote_at(self.lines[self.cy])
        link = None if q else self.link_here()
        if link:  # a hyperlink: the entry it points at
            if link[2] == self.self_id:
                self.message = "that's this pericope"
            else:
                self.opening = (link[2], None)
            return
        para = None if (q or self.stack) else self.para_here()
        if q:
            ref, _, mask = q
            at = mask[0] if mask else None
        elif para:  # a paraphrase: the block it paraphrases
            ref, at = para[1], None
        else:  # inside a quote: where the cursor is, in its source's draft
            ref, at = self.cur_id, self.offset_at(self.cy, self.cx)
            if self.vmode:
                at = store.view_to_draft(store.block_draft(self.library, ref), self.view_mask(), at)
        seen = set()
        while store.quoted(self.library.get(ref)) and ref not in seen:  # a quote of a quote: what it shows
            seen.add(ref)
            ref, mask = store.quoted(self.library[ref])
            at = mask[0] if mask else None
        if ref not in self.library or ref in seen:
            self.message = "its source is gone"
            return
        if not self.library[ref]["entry"]:  # a block inside an entry: that entry, at it
            blocks = {i: e["block"] for i, e in self.library.items()}
            home, start = store.home_of(blocks, ref)
            if home is None:
                self.message = "it's in no pericope"
                return
            text = isinstance(self.library[ref]["content"], str)
            ref, at = home, start + (min(at, len(self.library[ref]["content"])) if text and at else 0)
        if ref == self.self_id:
            self.message = "that's this pericope"
            return
        self.opening = (ref, at)

    def quote_here(self):
        """The quote selected, else the one the cursor's in: its (target, quote id), or None."""
        q = self.quote_at(self.lines[self.cy])
        if not q and self.stack:
            f = self.stack[-1]
            q = self.quote_at(f.lines[f.anchor])
        return (q[0], q[1]) if q and q[1] else None

    def toggle_show(self, key: str) -> None:
        """Show (or hide) one of the quote's properties in its top line."""
        _, qid = self.quote_here()
        show = self.show_of(qid)
        try:
            h, record = store.set_quote_show(qid, [k for k in show if k != key] if key in show else show + [key])
        except store.StoreError as e:
            self.message = str(e)
            return
        self.base.update(h)
        self.step(record)
        self.refresh_library()

    def toggle_lock(self) -> None:
        """Lock writing through the quote (the one selected, else the one
        you're in), or unlock it: one undo step."""
        _, qid = self.quote_here()
        on = not store.quote_lock(self.library.get(qid))
        if self.dirty():
            self.save()
        try:
            h, record = store.set_quote_lock(qid, on)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.base.update(h)
        self.step(record)
        self.refresh_library()
        self.message = "no writing through it now" if on else "writing through it again"

    def ask_delete(self) -> None:
        """Delete this entry: asked first (it can't be undone); confirm_key answers."""
        title = self.library.get(self.self_id, {}).get("title", "this pericope")
        self.confirming = "delete"
        self.message = f"delete '{title}'? y deletes it for good · any other key keeps it"

    def confirm_key(self, name) -> bool:
        """The key after a question: y does it. Returns True when the editor
        should close (the entry is gone)."""
        what, self.confirming = self.confirming, None
        if name != "y":
            self.message = "kept"
            return False
        if what == "delete":
            try:
                self.deleted = store.delete_entry(self.self_id)
            except store.StoreError as e:
                self.message = str(e)
                return False
            return True
        return False

    def detach(self) -> None:
        """Quote → text: a plain copy of what it shows, no longer live."""
        if self.dirty():
            self.save()
        qid = self.quote_at(self.lines[self.cy])[1]
        try:
            text, h, record = store.detach(qid)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.base.update(h)
        self.step(record)
        lines = text.split("\n")
        self.lines[self.cy:self.cy + 1] = lines
        self.bids[self.cy:self.cy + 1] = [qid] * len(lines)
        self.cx = 0
        self.refresh_library()
        self.message = "turned into text"

    def pop_out(self) -> str | None:
        """Block → quote: this block (text, a picture: anything but a quote)
        moves to an entry of its own, quoted here;
        with a selection, just that, nested where it was (nest_out).
        Returns the new entry's id (None if the store refused)."""
        if self.dirty():
            self.save()
        if self.selection():
            part = self.selected_part()
            if part is None:
                self.message = "select within one block of text"
                return None
            if part[1] or part[3]:
                return self.nest_out(*part)
        line = self.lines[self.cy]
        bid = atom_id(line) if is_atom(line) else self.bids[self.cy]  # (a block on a line of its own, as an image: its id)
        try:
            entry, h, record = store.pop_out(bid)
        except store.StoreError as e:
            self.message = str(e)
            return None
        self.base.update(h)
        self.step(record)
        top, end = (self.cy, self.cy) if is_atom(line) else self.block_at(self.cy)
        self.lines[top:end + 1] = [quote_line(entry, bid)]
        self.bids[top:end + 1] = [None]
        self.cy, self.cx = top, 0
        self.refresh_library()
        self.message = "popped out into its own pericope"
        return entry

    def selected_part(self):
        """The selection, inside one block of text: (that block's id, its text
        before, the selection, its text after), else None."""
        (y1, x1), (y2, x2) = self.selection()
        bid = self.bids[y1]
        if bid is None or any(self.bids[i] != bid for i in range(y1, y2 + 1)):
            return None
        top, end = self.block_at(y1)
        text = "\n".join(self.lines[top:end + 1])
        at = self.offset_in_block
        a, b = at(y1, x1), at(y2, x2)
        middle = text[a:b].strip()
        return (bid, text[:a].rstrip(), middle, text[b:].lstrip()) if middle else None

    def nest_out(self, bid: str, before: str, middle: str, after: str) -> str | None:
        """The selection → a quote of a new entry holding it, nested in its
        block (store.nest_out). Returns the new entry's id."""
        try:
            entry, h, record = store.nest_out(bid, before, middle, after)
        except store.StoreError as e:
            self.message = str(e)
            return None
        self.base.update(h)
        self.step(record)
        self.refresh_library()
        self.load_text(store.block_draft(self.library, self.cur_id))
        self.saved = self.snapshot()
        self.anchor = None
        self.cy = next(i for i, l in enumerate(self.lines) if (q := self.quote_at(l)) and q[0] == entry)
        self.cx, self.unit_side = 0, None
        self.message = "turned into a quote, nested here"
        return entry

    # --- hyperlinks -----------------------------------------------------
    def selected_span(self):
        """The selection, inside one block of text: (that block's id, its text
        in the buffer, [start, end] of the selection in it, space at its edges
        left out), else None."""
        (y1, x1), (y2, x2) = self.selection()
        bid = self.bids[y1]
        if bid is None or any(self.bids[i] != bid for i in range(y1, y2 + 1)):
            return None
        top, end = self.block_at(y1)
        text = "\n".join(self.lines[top:end + 1])
        at = self.offset_in_block
        a, b = at(y1, x1), at(y2, x2)
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        return (bid, text, [a, b]) if a < b else None

    def link_entry(self) -> None:
        """Link to an entry: pick the entry the selection points to (or + new
        entry, made with what you typed as its title)."""
        if self.dirty():
            self.save()
        span = self.selected_span()
        if span is None:
            self.message = "select some text in one block"
            return
        refs = sorted((r for r, e in self.library.items() if e["entry"] and r != self.self_id), reverse=True)
        bid, text, (a, b) = span
        picker = Picker(self.library, refs, pinned=[(NEW, new_label)])
        picker.sel = picker.first_result()
        self.palette = Menu("link", picker=picker, span=span)

    def link_to(self, span: tuple, to: str | None, title: str) -> None:
        """The selection becomes a hyperlink to entry `to` (None: a new entry titled `title`)."""
        bid, text, at = span
        try:
            target, record = store.link_text(bid, text, at, to, title)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        self.anchor = None
        self.stale = True
        self.message = f"linked to {self.library.get(target, {}).get('title', 'a pericope')}"

    def remove_link(self) -> None:
        """Remove link: the text stays, no longer pointing anywhere."""
        if not self.link_here():
            return
        _, _, to, link = self.link_here()
        try:
            record = store.unlink_text(self.bids[self.cy], to, link["at"])
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        self.stale = True
        self.message = "link removed"

    def pop_out_open(self) -> None:
        """Turn into a quote, then Open it: step into the new entry."""
        entry = self.pop_out()
        if entry:
            self.opening = (entry, None)

    def quote_new(self, title: str) -> None:
        """+ new entry in the quote search: a new entry (titled `title`),
        quoted at the cursor, and stepped into. One undo step takes back the
        quote and the entry; came_back does it for you if nothing's written."""
        if self.dirty():
            self.save()
        try:
            ref, record = store.new_entry(title, self.cur_id)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        self.joining = True  # the quote joins the step just made
        self.insert_quote(ref)
        self.save()
        self.made = (ref, len(self.undo))
        self.opening = (ref, None)

    def quote_promoted(self, ref: str) -> None:
        """Enter on a block inside an entry, in the quote search: it becomes
        an entry of its own (store.pop_out, as Turn into a quote does there),
        quoted where it was and here. One undo takes back both."""
        if self.dirty():
            self.save()
        try:
            entry, _, record = store.pop_out(ref)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        self.joining = True  # the quote joins the step just made
        self.insert_quote(entry)
        self.save()
        self.message = "a pericope of its own now, quoted here and where it was"

    def quote_masked(self, home: str, ref: str) -> None:
        """Shift+Enter on a block inside an entry, in the quote search: a
        quote of its entry, masked to just that block (widen it with Edit
        mask). One undo takes it back."""
        self.insert_quote(home)
        self.save()  # (the quote block made, to mask)
        self.refresh_library()
        qid = atom_id(self.lines[self.cy - 1]) if self.cy > 0 else None
        if not qid or qid not in self.library:
            return
        try:
            h, record = store.mask_quote_to(qid, ref)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.base.update(h)
        self.joining = True
        self.step(record)
        self.refresh_library()

    def open_backlinks(self) -> None:
        """The blocks pointing at this entry, oldest first, in a list: what
        kind, from where, when. Enter opens that entry at it."""
        found = self.backlinks()
        if not found:
            self.message = "nothing points here yet"
            return
        def label(k):
            x = found[int(k)]
            where = self.library.get(x["home"], {}).get("title", "?")
            when = store.pretty_time(x["created"]) if x["created"] else "undated"
            return f"{store.BACKLINK_NAMES[x['kind']][0]} in {where}", when
        self.palette = Menu("backlinks", picker=Picker(self.library, [str(n) for n in range(len(found))], label=label),
                            found=found)

    def open_kinds(self, typed: str = "") -> None:
        """The kinds picker, from the kinds line: the kinds (blue), newest
        first, filtered by what's typed (`typed`, to start with), and + new
        kind, named with it. Enter: the block is one; Shift+Enter: it isn't."""
        refs = sorted((k for k in store.kind_ids(self.library) if k != self.self_id), reverse=True)
        picker = Picker(self.library, refs, pinned=[(NEW, new_kind_label)])
        picker.blue = self.ink.blue
        picker.footer = lambda k: "↵ make it, and it is one · ⇧↵ … it isn't" if k == NEW else "↵ it is one · ⇧↵ it isn't"
        for ch in typed:
            picker.key(ch)
        picker.sel = picker.first_result()
        self.palette = Menu("kinds", picker=picker)

    def answer_kind(self, kind: str | None, answer: bool | None, name: str = "") -> None:
        """Say what the open block is (store.set_kind): `kind` is one (True),
        isn't (False) or no answer (None); `kind` None: a new kind called
        `name`. One undo step, the kind made included. The kinds line's
        cursor goes to its + (to add another)."""
        if self.dirty():
            self.save()
        try:
            _, record = store.set_kind(self.self_id, kind, answer, name)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.step(record)
        self.refresh_library()
        if self.fedit is not None and answer is not None:
            self.fedit.x = len(self.kind_chips(True)) - 1

    def follow_backlink(self, x: dict) -> None:
        """Open the entry backlink `x` is in, at it (on the trail, as Open it)."""
        self.fedit = None
        if x["home"] == self.self_id:
            self.message = "that's in this pericope"
            return
        if self.dirty():
            self.save()
        self.opening = (x["home"], x["at"])

    def came_back(self, ref: str) -> None:
        """Back from entry `ref`, stepped into: if + new entry made it and it
        was left empty (so it's discarded), its quote goes too, as if it never
        happened."""
        made, self.made = self.made, None
        if made == (ref, len(self.undo)) and not self.library.get(ref, {}).get("entry"):
            self.restore(True)
            if len(self.undo) < made[1]:  # undone (not refused): nothing to redo either
                self.redo.pop()
                self.message = "nothing written, no new pericope"

