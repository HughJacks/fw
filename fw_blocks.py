"""fw_blocks — blocks selected whole: part of the editor (a mixin of
fw_edit.Editor, whose state it reads).

In the block being edited (the entry, or a quote's source you're in) every
box is a block you can select whole ("blocks", a Picked): a block of text, a
quote, or a container with all it holds (fw_layout.block_units; at the
entry's level, the numbered boxes). Esc selects the block you're in (inside
a quote, Esc again selects the quote around it), and
Shift+↑/↓ grows the selection a block at a time; a text selection that
reaches another block becomes one of whole blocks (back inside the block
it began in, it's text again). While blocks are selected the text cursor
hides and the edge at the moving end is heavy: ↑/↓ from that edge goes
inside the block (the ghost shows where), the other way steps out.

Copy, cut, delete, typing and paste act on the blocks whole, as they do on
a quote selected by the arrows. The rich clipboard: copied blocks are kept
as data (store.save_clip, so it outlasts the session), each a unit shaped
like a block's content, with the id of the block it is: {"text", "links"}
for a block of text, {"quote", "shown"} for a quote (its mask, top line and
inner masks with it), {"image", "shown"} for an image (its file, and its path as its text), {"blocks"} for a
container. Pasted (the rule,
2026-10-25): ^V makes a live quote of each (a quote copied, a copy of that
quote); ^⇧V a static copy, new blocks of plain text (a quote as the text it
showed), links and nesting kept; after a cut, ^V moves the blocks themselves
back, the same ids (the store keeps cut blocks while the clipboard holds
them, store.clip_holds). New blocks go in the store loose and the save
takes them in. The system clipboard gets their text, a blank line apart; once
it holds something else, a paste is that text.
"""

import copy

import fw_store as store
from fw_menu import RUNS
from fw_layout import SHOW, block_units, many_blocks, paths_of
from fw_state import Picked
from fw_store import IMAGE_RE, MARKS, image_line, parse_draft, parse_nest, quote_line


def clip_text(units: list) -> str:
    """Clipped blocks as plain text: a quote as what it showed, the blocks a blank line apart."""
    return "\n\n".join(clip_text(u["blocks"]) if "blocks" in u else u.get("text", u.get("shown", ""))
                       for u in units)


def trimmed(text: str, spans: list) -> dict:
    """A block of text as clipped: without blank lines at its edges (as the
    store keeps it), its links moved to match."""
    lines = text.split("\n")
    start = next((k for k, l in enumerate(lines) if l.strip()), len(lines))
    end = len(lines) - next((k for k, l in enumerate(reversed(lines)) if l.strip()), len(lines))
    shift, body = sum(len(l) + 1 for l in lines[:start]), "\n".join(lines[start:end])
    at = [[max(a - shift, 0), min(b - shift, len(body))] for a, b, *_ in spans]
    return {"text": body, "links": [{"to": to, "at": span} for (_, _, to, _), span in zip(spans, at)
                                     if span[0] < span[1]]}


class BlockPicking:
    def units(self) -> list:
        return block_units(self.bids, paths_of(self.lines, self.bids, self.nest))

    def unit_of(self, li: int, units=None) -> int:
        return next(n for n, (s, e) in enumerate(units or self.units()) if s <= li <= e)

    def can_pick(self) -> bool:
        """Blocks can be selected whole where they're boxed: the entry's, and a
        quote's of more than one block (of one, the block you're in is the
        quote); not in a masked view, nor while masking."""
        return (bool(self.self_id) and self.vmode is None and self.medit is None
                and (not self.stack or many_blocks(self.bids)))

    def picked_span(self) -> tuple:
        """The blocks selected, as (first, last) indexes into units()."""
        return tuple(sorted((self.picked.anchor, self.picked.at)))

    def picked_lines(self):
        """The lines of the blocks selected whole, (first, last), else None: the
        blocks picked, or the quote the arrows selected."""
        if self.picked is not None:
            units = self.units()
            lo, hi = self.picked_span()
            return units[lo][0], units[hi][1]
        if self.on_atom() and self.anchor is None and self.medit is None:
            return self.cy, self.cy
        return None

    def pick(self, anchor: int, at: int, edge: str, text=None) -> None:
        """Select blocks `anchor` to `at` whole; the cursor waits at `at`'s heavy edge."""
        self.picked = Picked(anchor, at, edge, (self.cy, self.cx), text)
        self.anchor = None
        self.place_at_picked()

    def place_at_picked(self) -> None:
        s, e = self.units()[self.picked.at]
        self.cy, self.cx = (s, 0) if self.picked.edge == "top" else (e, 0)
        self.unit_side = None
        self.stale = True

    def pick_here(self) -> None:
        """Esc: select the block the cursor's in whole."""
        u = self.unit_of(self.cy)
        self.pick(u, u, "top")

    def pick_all(self) -> bool:
        """^A with more than one block: all of them, whole."""
        n = len(self.units())
        if not self.can_pick() or n < 2:
            return False
        self.pick(0, n - 1, "bottom")
        return True

    def snap_to_blocks(self) -> None:
        """After Shift+a move: a text selection that reaches another block
        selects whole blocks, from the one it began in."""
        if self.anchor is None or not self.can_pick():
            return
        units = self.units()
        a, b = self.unit_of(self.anchor[0], units), self.unit_of(self.cy, units)
        if a != b:
            self.pick(a, b, "bottom" if b > a else "top", text=self.anchor)

    # --- keys ----------------------------------------------------------
    def key_blocks(self, name: str, act) -> bool:
        p, units = self.picked, self.units()
        if not (0 <= p.anchor < len(units) and 0 <= p.at < len(units)):
            self.picked = None  # the buffer changed under it
            return self.key_text(name, act)
        if self.refuse(act):  # (through a locked quote: selecting and copying only)
            return False
        if act == "escape" and self.stack:  # inside a quote: the quote around them, selected
            self.picked = None
            self.leave()
            self.unit_side = None
        elif act == "escape":
            self.picked = None
            self.cy = min(p.back[0], len(self.lines) - 1)
            self.cx = min(p.back[1], len(self.lines[self.cy]))
        elif act in ("select_up", "select_down", "select_page_up", "select_page_down"):
            self.grow(-1 if act in ("select_up", "select_page_up") else 1, units)
        elif act is not None and act.startswith("select_") and act != "select_all":
            pass  # Shift+←/→: the blocks stay selected
        elif act in ("copy", "cut", "paste", "paste_static"):
            getattr(self, act)()
        elif act in ("backspace", "delete", "delete_word"):
            self.delete_blocks()
        elif act is not None and (len(act) == 1 or act in ("newline", "line_break", "nest_in", "tab")):
            self.replace_blocks()
            return False if act in ("newline", "line_break", "nest_in") else self.key_text(name, act)
        elif act in ("up", "down", "page_up", "page_down"):
            return self.step_picked(act in ("up", "page_up"), units, name, act)
        elif act in RUNS.values() and p.anchor != p.at:
            self.message = "select within one block"  # (a command acts on one block)
        elif act in ("left", "word_left", "home", "right", "word_right", "end"):
            lo, hi = self.picked_span()
            self.picked = None
            back = act in ("left", "word_left", "home")
            s, e = units[lo] if back else units[hi]
            self.cy, self.cx = (s, 0) if back else (e, 0 if self.is_atom(e) else len(self.lines[e]))
            self.unit_side = ("before" if back else "after") if self.is_atom(self.cy) else None
        else:  # anything else (undo, the menu, a command on the one block): as in the text, from where it is
            self.picked = None
            return self.key_text(name, act)
        self.stale = True
        return False

    def grow(self, d: int, units: list) -> None:
        """Shift+↑/↓: one block more (or fewer) at the moving end."""
        p = self.picked
        at = p.at + d
        if not 0 <= at < len(units):
            return
        s, e = units[at]
        if at == p.anchor and p.text is not None and not self.is_atom(s):
            self.picked = None  # back in the block it began in: a text selection again
            self.anchor = p.text
            self.cy, self.cx = (e, len(self.lines[e])) if d < 0 else (s, 0)
            return
        p.at = at
        p.edge = "bottom" if at > p.anchor else "top" if at < p.anchor else ("top" if d < 0 else "bottom")
        self.place_at_picked()

    def step_picked(self, up: bool, units: list, name: str, act) -> bool:
        """↑/↓ with blocks selected: of several, just the one at that end; from
        one's heavy edge, inside it; the other way, out to the next."""
        p = self.picked
        lo, hi = self.picked_span()
        if lo != hi:
            self.picked = Picked(lo if up else hi, lo if up else hi, "top" if up else "bottom", p.back)
            self.place_at_picked()
            return False
        s, e = units[p.at]
        self.picked = None
        if s == e and self.is_atom(s):  # a quote: selected as the arrows select one, and on from there
            self.cy, self.cx, self.unit_side = s, 0, "before" if p.edge == "top" else "after"
            return self.key_text(name, act)
        if up == (p.edge == "bottom"):  # in
            self.ensure_layout()
            self.goto_row(self.landing(p)[0], self.want_x(p), forward=not up)
            return False
        li = s if up else e  # out, past its edge
        self.cy, self.cx = li, 0 if up or self.is_atom(li) else len(self.lines[li])
        self.unit_side = ("before" if up else "after") if self.is_atom(li) else None
        return self.key_text(name, act)

    def want_x(self, p: Picked) -> int:
        return self.goal_x if self.goal_x is not None else 0 if p.edge == "top" else 10 ** 6

    def landing(self, p: Picked) -> tuple:
        """Where ↑/↓ from the heavy edge of the one block selected goes in: (row, the row's text or None)."""
        first, last = self.unit_rows[p.at]
        r = self.past_gaps(first if p.edge == "top" else last, 1 if p.edge == "top" else -1)
        return r, self.rows[r].drawn

    def picked_ghost(self):
        """With one block of text selected: (row, column, character) where ↑/↓ from its heavy edge lands, else None."""
        p = self.picked
        if p.anchor != p.at:
            return None
        r, drawn = self.landing(p)
        if drawn is not None:  # a quote at that edge (in a container): that's what gets selected
            return None
        li, start = self.rows[r].line, self.rows[r].start
        col = self.col_at(r, self.want_x(p))
        line = self.lines[li]
        ch = line[col] if col < len(line) and col < self.rows[r].end else " "
        return r, self.text_x(r) + self.col_x(li, start, col), SHOW.get(ch, ch) if ch != "\t" else " "

    # --- acting on them ------------------------------------------------
    def clip_units(self, s: int, e: int, level: int = 0) -> list:
        """Lines s..e, whole blocks, as clipped units (see the module's doc),
        `level` containers in."""
        units, i = [], s
        while i <= e:
            inside = lambda li: self.containers(li)[level:level + 1]
            j = i
            if inside(i):  # a container: all it holds
                while j < e and inside(j + 1) == inside(i):
                    j += 1
                units.append({"blocks": self.clip_units(i, j, level + 1), "id": inside(i)[0]})
            elif image := IMAGE_RE.fullmatch(self.lines[i]):
                iid = image.group(1)
                name = store.image_of(self.library.get(iid, {}).get("block"))
                units.append({"image": name, "shown": str(store.image_file(name)) if name else "", "id": iid})
            elif self.is_atom(i):
                target, qid, _ = self.quote_at(self.lines[i])
                b = self.library.get(qid, {}).get("block")
                units.append({"quote": copy.deepcopy(b["content"]) if store.quoted(b) else {"quote": target},
                              "shown": self.shown_line(self.lines[i]), "id": qid})
            else:
                last, text, spans = self.block_links(self.lines, self.bids, i)
                j = min(last, e)
                bid = self.bids[i] if self.bids[i] in self.library else self.cur_id  # (a block of plain text: itself)
                units.append({**trimmed("\n".join(self.lines[i:j + 1]), spans if j == last else []), "id": bid})
            i = j + 1
        return units

    def shown_line(self, line: str) -> str:
        """A quote line's text, as it shows."""
        target, qid, _ = self.quote_at(line)
        if qid in self.library:
            return store.shown_text(self.library, qid)
        return store.shown_text(self.library, target) if target in self.library else ""

    def copy_blocks(self, cut: bool = False) -> None:
        if self.dirty():
            self.save()  # (so each block copied is in the store, by its id)
        self.refresh_library()
        s, e = self.picked_lines()
        units = self.clip_units(s, e)
        text = clip_text(units)
        self.to_clipboard(text)
        store.save_clip({"text": text, "blocks": units, **({"cut": True} if cut else {})})
        self.message = f"copied {len(units)} block{'s' if len(units) > 1 else ''}" if self.picked else "copied"

    def cut_blocks(self) -> None:
        self.copy_blocks(cut=True)  # (held by the clipboard: their quotes elsewhere stay live, for the paste to move)
        self.delete_blocks()
        self.message = "cut"

    def delete_blocks(self) -> None:
        """Remove the blocks selected whole; the cursor goes to the start of the one after."""
        s, e = self.picked_lines()
        self.checkpoint("delete", force=True)
        del self.lines[s:e + 1]
        del self.bids[s:e + 1]
        if not self.lines:
            self.lines, self.bids = [""], [self.fresh()]
        self.picked = None
        self.cy = min(s, len(self.lines) - 1)
        self.cx = 0 if s < len(self.lines) or self.is_atom(self.cy) else len(self.lines[self.cy])
        self.unit_side = None

    def replace_blocks(self) -> None:
        """Typing over blocks selected whole: one new, empty block in their place."""
        s, e = self.picked_lines()
        self.checkpoint("insert", force=True)
        self.lines[s:e + 1] = [""]
        self.bids[s:e + 1] = [self.fresh()]
        self.picked = None
        self.cy, self.cx = s, 0
        self.unit_side = None
        self.joining = True  # the typing joins this step

    def movable(self, units: list) -> bool:
        """Blocks cut can be moved back: each is held by nothing (the clipboard
        keeps it), or gone and made again from the clip."""
        return all(u.get("id") and (u["id"] not in self.library or store.loose(self.library, u["id"])) for u in units)

    def lay_clip(self, units: list, made: dict, outer: str | None = None, mode: str = "static") -> tuple:
        """Clipped units as blocks for the buffer: (their lines and bids, its
        nesting for them, their ids in order). `mode`: "quote", a new quote of
        each (a quote, a copy of it); "move", the blocks themselves, by id;
        "static", new blocks of plain text. Each new block goes in `made`, to
        be put in the store. What's gone since comes back as static text."""
        lines, bids, nest, ids = [], [], {}, []
        for u in units:
            i, src = store.new_id(self.taken() | set(made)), u.get("id")
            if mode == "move" and src in self.library:  # the block itself, as the store has it
                draft = "\n".join(store.child_lines(self.library, [src]))
                (l, b), n, i = parse_draft(draft), parse_nest(draft), src
                nest.update(n)
            elif mode == "quote" and "quote" not in u and src in self.library:
                made[i] = store.new_block(i, {"quote": src})
                l, b = [quote_line(src, i)], [None]
            elif "blocks" in u:
                made[i] = None  # (its id taken)
                l, b, n, kids = self.lay_clip(u["blocks"], made, i, "static" if mode == "static" else "quote")
                made[i] = store.new_block(i, kids)
                nest.update(n)
            elif u.get("image"):  # (a static copy, or one gone since: the same picture, a new block)
                made[i] = store.new_block(i, {"image": u["image"]})
                l, b = [image_line(i)], [None]
            elif "quote" in u and mode != "static" and u["quote"]["quote"] in self.library:
                made[i] = store.new_block(i, copy.deepcopy(u["quote"]))
                l, b = [quote_line(u["quote"]["quote"], i)], [None]
            else:
                text = u.get("text", u.get("shown", ""))
                plain = "".join(c for c in text if c not in MARKS)
                kept = [link for link in u.get("links", []) if link["to"] in self.library] if plain == text else []
                made[i] = store.new_block(i, plain, links=kept)
                l = plain.split("\n")
                b = [i] * len(l)
            if outer:
                nest[i] = outer
            lines, bids, ids = lines + l, bids + b, ids + [i]
        return lines, bids, nest, ids

    def paste_place(self) -> tuple:
        """Where blocks pasted now go: (first line, lines they replace, the
        container they go in, or the block of text they go inside of, else
        None). Blocks selected whole: before them from their heavy top, after
        them from their heavy bottom; a quote the arrows selected, likewise; an
        empty block, in its place; in a block's text, inside it, splitting it
        at the cursor (it becomes a container, holding its text either side)."""
        units = self.units()
        if self.picked is not None:
            lo, hi = self.picked_span()
            return (units[lo][0] if self.picked.edge == "top" else units[hi][1] + 1), 0, None, None
        if self.on_atom():
            return (self.cy if self.unit_side == "before" else self.cy + 1), 0, self.outer(self.cy), None
        top, last = self.block_at(self.cy)
        if top == last and self.lines[top] == "":
            return top, 1, self.outer(top), None
        return top, last - top + 1, None, self.bids[self.cy]

    def paste_blocks(self, units: list, mode: str = "static") -> None:
        """Clipped blocks back, where paste_place says, as `mode` (lay_clip)
        has them. New ones go in the store loose first (with their links,
        masks, nesting), and moved ones are loose already: the save takes them
        in. One undo takes them all back out, the block they went inside of
        as it was (moved ones loose again, the clipboard still holding them)."""
        if self.dirty():
            self.save()
        self.refresh_library()
        at, gone, outer, into = self.paste_place()
        wrap = into in self.library  # (a block of plain text has no child for its text: its own blocks, then)
        made = {}
        lines, bids, nest, _ = self.lay_clip(units, made, into if wrap else outer, mode)
        if into is not None:  # its text before the cursor and after it, each a block of its own around them
            head = self.lines[at:self.cy] + [self.lines[self.cy][:self.cx]]
            tail = [self.lines[self.cy][self.cx:]] + self.lines[self.cy + 1:at + gone]
            for piece, first in ((head, True), (tail, False)):
                if any(line.strip() for line in piece):
                    i = store.new_id(self.taken() | set(made))
                    made[i] = None  # (its id taken; the save makes it)
                    if wrap:
                        nest[i] = into
                    lines, bids = (piece + lines, [i] * len(piece) + bids) if first else (lines + piece, bids + [i] * len(piece))
        kept = store.subtree(self.library, self.cur_id) if self.cur_id in self.library else []
        undo = {"blocks": {**{i: None for i in made}, **{i: copy.deepcopy(self.library[i]["block"]) for i in kept}}}
        try:
            store.restore({"blocks": {i: b for i, b in made.items() if b is not None}}, tidy=False)
        except (store.StoreError, OSError, ValueError) as e:
            self.message = str(e)
            return
        self.step(undo)
        self.lines[at:at + gone] = lines
        self.bids[at:at + gone] = bids
        self.nest.update(nest)
        self.picked = None
        last = at + len(lines) - 1 - (len(tail) if into is not None and any(l.strip() for l in tail) else 0)
        self.cy = last
        self.cx = 0 if self.is_atom(self.cy) else len(self.lines[self.cy])
        self.unit_side = "after" if self.is_atom(self.cy) else None
        self.refresh_library()
        self.save()  # (taking them in at once: nothing else erases them loose)
