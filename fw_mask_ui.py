"""fw_mask_ui — masking mode: choosing what a quote shows, part of the editor
(a mixin of fw_edit.Editor, whose state it works on).

One mask over the flow. The quote being masked and every quote inside it,
read top to bottom, are one stream of text (`build_flow`), each quote inside
as it shows without this masking (anything its source hides is a locked …).
`[` and `]` act on that stream wherever the cursor is, as set operations on
its spans (fw_lens): a `]` inside a box ends what shows there, through every
box before it and none after. Each part of the stream (a "segment": the
quoted text, or a quote inside it, by the path of quote ids to it) is drawn
from the one mask: its text, hidden parts dim, the brackets that fall in it
(the implied ones at the very start and end only where masking started,
dim). Stored, the mask is split per block (`split_mask`): the quote's own
mask, and an inner mask for each quote inside it. No typing while masking.
"""

import copy

import fw_keys as keys
import fw_store as store
from fw_layout import box_plan, drawn, edge, many_blocks, paths_of
from fw_state import Frame, Masking
from fw_store import (BLOCK_RE, CLOSE, ELLIPSIS, IMAGE_RE, MAX_DEPTH, OPEN, QUOTE_RE, block_draft, is_atom, parse_draft,
                      parse_nest)

MASK_HELP = "masking · [ shows from here · ] hides from here · esc done"
NO_TYPING = "masking · no typing here · esc when done"
TEXT_EDITS = {"newline", "line_break", "nest_in", "paste", "tab", "cut", "delete_word", "backspace", "delete"}
STAND_IN = "\x00"  # a quote too deep (or a loop) in the stream: one place, shown or not


# --- the flow (pure) -----------------------------------------------------------

def nested_view(library: dict, qid: str, between: dict) -> dict:
    """Quote `qid` inside the quote being masked, as it shows without this
    masking: its own mask narrowed by the quotes `between` (their inner masks)."""
    target, own = store.quoted(library[qid])
    base = store.intersect(own, between.get(qid))
    draft = block_draft(library, target)
    return {"target": target, "draft": draft, "base": base, "text": store.view(draft, base)}


def build_flow(library: dict, qid: str, depth: int) -> dict:
    """The stream masking works on: `text`, and for each of its characters the
    (segment, offset in that segment's text) it is (`own`). Each segment has
    its `text`, `index` (offset -> place in the stream), and the quote lines in
    it, `quotes`: (quote id, line start, line end, stream start, stream end).
    `depth`: how many boxes deep the quote being masked is (a quote inside
    it is a box deeper, or two in a container; past MAX_DEPTH, a stand-in)."""
    target = store.quoted(library[qid])[0]
    text, own, segs, locked = [], [], {}, set()

    def put(key, local, ch):
        segs[key]["index"][local] = len(text)
        if ch == ELLIPSIS or (ch == "\n" and text and text[-1] == ELLIPSIS and len(text) - 1 in locked):
            if key:  # what a source hides, in a quote inside: the brackets look through it
                locked.add(len(text))
        text.append(ch)
        own.append((key, local))

    def walk(key, seg_text, d, between, path):
        seg = segs[key]
        seg.update(text=seg_text, index={}, quotes=[])
        lines, off = seg_text.split("\n"), 0
        for n, line in enumerate(lines):
            m = QUOTE_RE.fullmatch(line)
            image = IMAGE_RE.fullmatch(line)  # (an image: one place, as a stand-in is)
            if BLOCK_RE.fullmatch(line):
                pass
            elif m or image:
                q, start = (image.group(1) if image else m.group(2)), len(text)
                inner = store.quoted(library.get(q)) if q and not image else None
                within = (image.group(2) if image else m.group(3)).split()
                qd = d + 1 + sum(d + k + 1 <= MAX_DEPTH for k in range(len(within)))  # its box's depth (its containers' boxes around it)
                if inner and inner[0] in library and inner[0] not in path and qd <= MAX_DEPTH:
                    v = nested_view(library, q, between)
                    child = key + (q,)
                    segs[child] = {"qid": q, "target": v["target"], "draft": v["draft"], "base": v["base"]}
                    walk(child, v["text"], qd, store.merge_inner(between, store.quote_inner(library[q])),
                         path + [v["target"]])
                    put(child, len(v["text"]), "\n")  # its end, in the stream
                else:
                    put(key, off, STAND_IN)
                seg["quotes"].append((q, off, off + len(line), start, len(text)))
            else:
                for i, ch in enumerate(line):
                    put(key, off + i, ch)
                if n < len(lines) - 1:
                    put(key, off + len(line), "\n")
            off += len(line) + 1
        seg["index"].setdefault(len(seg_text), len(text))

    segs[()] = {"target": target}
    walk((), block_draft(library, target), depth, {}, [target])
    return {"text": "".join(text), "own": own, "segs": segs, "locked": locked}


def shown_in(mask: list, n: int) -> list:
    """For each place of a stream n long, whether `mask` shows it."""
    v = [False] * n
    for o, c in store.spans_of(mask):
        v[o:c] = [True] * (c - o)
    return v


def runs(v: list) -> list:
    """A mask from what shows, place by place."""
    out, start = [], None
    for i, s in enumerate(v + [False]):
        if s and start is None:
            start = i
        elif not s and start is not None:
            out += [start, i]
            start = None
    return out


def initial_mask(flow: dict, library: dict, qid: str) -> list:
    """The stream's mask from what's stored: the quote's own mask, and its
    inner ones (a quote inside shows only where its line shows)."""
    own, inner = store.quoted(library[qid])[1], store.quote_inner(library[qid])
    n = len(flow["text"])
    v, gate = [False] * n, {(): True}
    for key in sorted(flow["segs"], key=len):  # outer segments first
        seg = flow["segs"][key]
        if key == ():
            m, to_draft = own, (lambda p: p)
        else:
            m = inner.get(seg["qid"])
            to_draft = (lambda p, seg=seg: store.view_to_draft(seg["draft"], seg["base"], p))
        spans = None if m is None else store.spans_of(m)
        shows = lambda a, b: spans is None or any(o <= a and b <= c for o, c in spans)
        for local, i in seg["index"].items():
            if i < n and flow["own"][i] == (key, local):
                p = to_draft(local)
                v[i] = gate[key] and shows(p, p + 1)
        for q, ls, le, fs, fe in seg["quotes"]:
            covered = gate[key] and shows(to_draft(ls), to_draft(le))
            if key + (q,) in flow["segs"]:
                gate[key + (q,)] = covered
            elif fe > fs:
                v[fs] = covered
    for i in sorted(flow["locked"]):  # locked: as what comes before it
        v[i] = v[i - 1] if i else False
    return runs(v)


def line_ends(text: str, at: int, forward: bool, quotes: set) -> int:
    """From the edge of a quote line: the end of the text line before it (or
    the start), else the start of the text line after it (or the end), past
    marker and quote lines; so a span can take in a quote line whole."""
    lines, starts, off = text.split("\n"), [], 0
    for line in lines:
        starts.append(off)
        off += len(line) + 1
    n = next(i for i, s in enumerate(starts) if s <= at < s + len(lines[i]) + 1) if at < len(text) else len(lines)
    rng = range(n + 1, len(lines)) if forward else range(n - 1, -1, -1)
    for i in rng:
        if not (BLOCK_RE.fullmatch(lines[i]) or is_atom(lines[i])):
            return starts[i] if forward else starts[i] + len(lines[i])
    return len(text) if forward else 0


def split_mask(flow: dict, mask: list) -> tuple:
    """The stream's mask, stored per block: (the quote's own mask, its text
    as masked; {quote id: (its target's text, its inner mask or None)})."""
    n = len(flow["text"])
    v = shown_in(mask, n)
    own, inner = None, {}
    for key, seg in flow["segs"].items():
        text = seg["text"]
        units = [None] * len(text)  # what shows: True, False, or None (nothing to show: a marker, a locked …)
        for local, i in seg["index"].items():
            if local < len(text) and i < n and flow["own"][i] == (key, local) and i not in flow["locked"]:
                units[local] = v[i]
        starts, ends = set(), set()
        for q, ls, le, fs, fe in seg["quotes"]:
            units[ls:le] = [any(v[fs:fe])] * (le - ls)
            starts.add(ls)
            ends.add(le)
        anchors, on, last = [], False, 0
        for i, u in enumerate(units):
            if u is None:
                continue
            if u and not on:
                anchors.append(line_ends(text, i, False, starts) if i in starts else i)
                on = True
            elif not u and on:
                anchors.append(line_ends(text, last - 1, True, ends) if last in ends else last)
                on = False
            if u:
                last = i + 1
        if on:
            anchors.append(line_ends(text, last - 1, True, ends) if last in ends else len(text))
        if key == ():
            own = (text, store.normalize(text, anchors) if anchors else [])
        else:
            draft, base = seg["draft"], seg["base"]
            m = store.intersect(base, [store.view_to_draft(draft, base, a) for a in anchors])
            m = store.normalize(draft, m) if m else []
            inner.setdefault(seg["qid"], (draft, None if m == store.normalize(draft, base) else m))
    return own, inner


def render(flow: dict, mask: list, key: tuple) -> tuple:
    """Segment `key` as masking draws it: (its text with the brackets that fall
    in it drawn in, and for each line but marker lines, None for a quote line,
    else (a code per character, the segment offset per character, the offset
    of its end)). Codes: "s" shown, "h" hidden, "o"/"c" a bracket you typed,
    "O"/"C" an implied one (only where masking started)."""
    seg, n = flow["segs"][key], len(flow["text"])
    v = shown_in(mask, n)
    marks = {}
    for a, p in enumerate(mask):
        opener = a % 2 == 0
        implied = (a == 0 and p == 0) or (a == len(mask) - 1 and p == n)
        i = p if opener else p - 1
        if (implied and key) or not 0 <= i < n or flow["own"][i][0] != key:
            continue
        local = flow["own"][i][1] + (0 if opener else 1)
        marks.setdefault(local, []).append((not opener, OPEN if opener else CLOSE, implied, a))
    out, meta, off = [], [], 0
    for line in seg["text"].split("\n"):
        if BLOCK_RE.fullmatch(line) or is_atom(line):
            out.append(line)
            if not BLOCK_RE.fullmatch(line):
                meta.append(None)
            off += len(line) + 1
            continue
        chars, codes, locs = [], [], []
        for c in range(len(line) + 1):
            for _, kind, implied, a in sorted(marks.get(off + c, []), reverse=True):  # closers first
                chars.append(kind)
                codes.append(("O" if kind == OPEN else "C") if implied else ("o" if kind == OPEN else "c"))
                locs.append(("bracket", a))
            if c < len(line):
                i = seg["index"].get(off + c)
                chars.append(line[c])
                codes.append("s" if i is not None and v[i] else "h")
                locs.append(off + c)
        out.append("".join(chars))
        meta.append((codes, locs, off + len(line)))
        off += len(line) + 1
    return "\n".join(out), meta


class MaskEditing:
    # --- small helpers the editor shares ----------------------------------
    def parent_quote(self):
        """The quote line, in the block below on the stack, that's open for editing."""
        f = self.stack[-1]
        return self.quote_at(f.lines[f.anchor])

    def mark_near(self, kinds) -> int | None:
        """The column of a mark of `kinds` at the cursor or just before it."""
        line = self.lines[self.cy]
        for col in (self.cx, self.cx - 1):
            if 0 <= col < len(line) and line[col] in kinds:
                return col
        return None

    def offset_at(self, li: int, col: int) -> int:
        return self.draft_offsets()[li] + col

    def place_at(self, q: int) -> None:
        """The cursor at offset q of the buffer's draft text."""
        offs = self.draft_offsets()
        li = max((i for i, o in enumerate(offs) if o <= q), default=0)
        self.cy, self.cx = li, min(max(q - offs[li], 0), len(self.lines[li]))

    # --- masking mode -------------------------------------------------------
    def edit_mask(self, at: int | None = None) -> None:
        """Masking mode on a quote: the one the cursor's on, else the one being
        edited (masks are stored on the quote where masking starts). `at`: where
        to start in its text (else the cursor)."""
        if self.on_atom() and self.enterable(self.cy):
            self.enter(self.cy)
            self.arrive()
        if not self.stack:
            self.message = "not in a quote"
            return
        if self.dirty():
            self.save()
        self.refresh_library()
        qid = self.parent_quote()[1]
        draft = block_draft(self.library, self.cur_id)
        if at is None:
            pos = self.offset_at(self.cy, self.cx)
            at = store.view_to_draft(draft, self.view_mask(), pos) if self.vmode else pos
        # one step to undo the whole edit: the buffer as it is, the quote and its text as stored
        kept = [qid, *store.subtree(self.library, self.cur_id)]
        self.step({"blocks": {i: copy.deepcopy(self.library[i]["block"]) for i in kept if i in self.library}})
        self.ensure_layout()
        flow = build_flow(self.library, qid, self.spans[self.frames[self.first_row[0]][-1]][2])
        self.vmode = None
        self.medit = Masking(qid, start=len(self.undo), depth=len(self.stack), keys=[()],
                             flow=flow, mask=initial_mask(flow, self.library, qid))
        self.mask_draw()
        self.place_flow(flow["segs"][()]["index"].get(at, 0))
        self.saved = self.snapshot()
        self.message = MASK_HELP

    def mask_lines(self, key: tuple) -> tuple:
        """(lines, bids, nest, meta, silent) of segment `key`, as masking draws it."""
        text, meta = render(self.medit.flow, self.medit.mask, key)
        lines, bids = parse_draft(text, self.taken())
        marked = {m.group(1) for m in BLOCK_RE.finditer(text)}  # (a view's text after a hidden marker has none of its own)
        return lines, bids, parse_nest(text), meta, {b for b in bids if b and b not in marked}

    def mask_draw(self) -> None:
        """Draw every level being masked from the one mask: the buffer, and the
        levels around it on the stack."""
        keys_ = self.medit.keys
        for k, key in enumerate(keys_[:-1]):
            f = self.stack[self.medit.depth + k]
            f.lines, f.bids, f.nest, f.meta, f.silent = self.mask_lines(key)
        self.lines, self.bids, self.nest, self.medit.meta, self.medit.silent = self.mask_lines(keys_[-1])
        self.cy = min(self.cy, len(self.lines) - 1)
        self.cx = min(self.cx, len(self.lines[self.cy]))
        self.stale = True

    def flow_at(self, li: int, col: int) -> int:
        """Where (li, col) of the buffer is in the stream."""
        meta = self.medit.meta[li] if li < len(self.medit.meta) else None
        seg = self.medit.flow["segs"][self.medit.keys[-1]]
        if meta is None:
            return 0
        codes, locs, end = meta
        local = next((l for l in locs[col:] if not isinstance(l, tuple)), end)
        return seg["index"].get(local, 0)

    def place_flow(self, p: int) -> None:
        """The cursor at stream place p, if it's in the buffer (just after any
        bracket there)."""
        own = self.medit.flow["own"]
        key = self.medit.keys[-1]
        for li, meta in enumerate(self.medit.meta):
            if meta is None:
                continue
            codes, locs, end = meta
            for col, l in enumerate(locs + [end]):
                if not isinstance(l, tuple) and self.medit.flow["segs"][key]["index"].get(l) == p:
                    self.cy, self.cx = li, col
                    return
        if p >= len(own):
            self.cy = len(self.lines) - 1
            self.cx = len(self.lines[self.cy])

    def set_mask(self, mask: list, p: int) -> None:
        """A new mask for the stream (a step to undo): drawn, stored, the cursor at p."""
        self.push_undo()
        self.anchor = None
        self.medit.mask = store.tidy_edit(self.medit.flow["text"], mask)
        self.mask_draw()
        self.place_flow(p)
        self.save_mask()

    def bracket(self, kind: str) -> None:
        """[ or ]: at the cursor, or around the selection (show it exactly, or
        hide it), on the stream: so across every box."""
        mask, n = self.medit.mask, len(self.medit.flow["text"])
        sel = self.selection()
        if sel:
            a, b = self.flow_at(*sel[0]), self.flow_at(*sel[1])
            self.set_mask(store.wrap(mask, a, b) if kind == "[" else store.minus(mask, a, b), a)
        else:
            p = self.flow_at(self.cy, self.cx)
            self.set_mask((store.open_at if kind == "[" else store.close_at)(mask, p, n), p)

    def unbracket_at(self, col: int) -> None:
        """Backspace on a bracket: it goes, and the spans either side of it join."""
        codes, locs, _ = self.medit.meta[self.cy]
        a = locs[col][1]
        self.set_mask(store.drop_anchor(self.medit.mask, a, len(self.medit.flow["text"])),
                      self.flow_at(self.cy, col))

    def save_mask(self) -> None:
        """Store the mask, per block: the quote's own, and its inner ones."""
        own, inner = split_mask(self.medit.flow, self.medit.mask)
        try:
            h, _ = store.set_quote_masks(self.medit.qid, own, inner)
            self.base.update(h)
        except store.StoreError as e:
            self.message = str(e)
        self.refresh_library()
        self.saved = self.snapshot()

    def mask_into(self, li: int, at_end: bool = False) -> None:
        """While masking: the cursor into the quote on line `li` (its text a
        part of the stream; nothing about it changes but where the cursor is)."""
        _, qid, _ = self.quote_at(self.lines[li])
        key = self.medit.keys[-1] + (qid,)
        if key not in self.medit.flow["segs"]:
            return  # a stand-in: nothing to go into
        self.stack.append(Frame(self.cur_id, self.lines, self.bids, self.saved, li, self.undo, self.redo,
                                self.vmode, self.nest, self.medit.meta, self.medit.silent))
        self.medit.keys.append(key)
        self.cur_id, self.vmode, self.undo, self.redo = self.medit.flow["segs"][key]["target"], None, [], []
        self.cy = self.cx = 0
        self.mask_draw()
        if at_end:
            self.cy = len(self.lines) - 1
            self.cx = len(self.lines[self.cy])
        self.saved = self.snapshot()
        self.anchor = None

    def mask_out(self) -> None:
        """While masking: the cursor back out of a quote inside, onto its line."""
        self.medit.keys.pop()
        f = self.stack.pop()
        self.cur_id, self.lines, self.bids, self.saved = f.id, f.lines, f.bids, f.saved
        self.vmode, self.undo, self.redo, self.nest = f.vmode, f.undo, f.redo, f.nest
        self.medit.meta, self.medit.silent = f.meta, f.silent
        self.cy, self.cx = f.anchor, 0
        self.anchor = None
        self.last_edit = None
        self.mask_draw()
        self.saved = self.snapshot()

    def masking_rows(self, key: tuple, path: list, depth: int, base: int) -> list:
        """While masking: drawn rows for the quote inside at segment `key`, as
        it's being masked (all its text, hidden parts dim, the brackets in it),
        in its box, its blocks boxed as they are at rest; `base` is the row it starts on."""
        seg = self.medit.flow["segs"][key]
        text, meta = render(self.medit.flow, self.medit.mask, key)
        rows = [edge(depth, "top", self.quote_label(seg["target"], self.show_of(seg["qid"])))]
        (lines, bids), nest = parse_draft(text), parse_nest(text)
        opened = []
        for line, m, p in zip(lines, meta, box_plan(bids, paths_of(lines, bids, nest), depth, many_blocks(bids))):
            for d in p.opens:
                opened.append((base + len(rows), d))
                rows.append(edge(d, "top", plain=True))
            if p.dot:
                self.dots.add(base + len(rows))
            q = QUOTE_RE.fullmatch(line)
            if m is None and IMAGE_RE.fullmatch(line):
                rows += self.image_rows(IMAGE_RE.fullmatch(line).group(1), p.depth, base + len(rows))
            elif m is None and q:
                child = key + (q.group(2),)
                if child in self.medit.flow["segs"]:
                    rows += self.masking_rows(child, path + [seg["target"]], p.depth, base + len(rows))
                else:
                    rows += self.quote_rows(q.group(1), path + [seg["target"]], p.depth, base + len(rows))
            else:
                rows += drawn(depth, line, self.inner(), "mask", m[0])
            self.close_boxes(opened, p.closes, rows, base=base)
        rows.append(edge(depth, "bottom"))
        self.spans.append((base, base + len(rows) - 1, depth))
        return rows

    def mask_flow(self, act: str, before: int) -> None:
        """While masking, arrows run through the quotes inside as if they were
        text: never stopping on one as a whole, straight in (or, coming out of
        one, straight on past it)."""
        forward = act in ("down", "right", "page_down", "word_right", "end")
        for _ in range(2 * MAX_DEPTH + 2):
            if not self.medit or not self.on_atom() or self.anchor is not None:
                return
            if len(self.stack) < before:  # just came out of it: on past
                before = len(self.stack)
                if act in ("up", "down", "page_up", "page_down"):
                    self.move_vert(1 if forward else -1)
                else:
                    (self.right if forward else self.left)()
            elif self.enterable(self.cy):
                self.enter(self.cy, at_end=not forward)
                if len(self.stack) == before:
                    return  # nothing to go into
                before = len(self.stack)
            else:
                return

    def jump(self, forward: bool) -> None:
        """Tab / Shift+Tab: to the next / previous bracket."""
        spots = [(li, c) for li, line in enumerate(self.lines) for c, ch in enumerate(line) if ch in (OPEN, CLOSE)]
        here = (self.cy, self.cx)
        nxt = [s for s in spots if s >= here] if forward else [s for s in spots if s < (here[0], here[1] - 1)]
        if nxt:
            self.cy, self.cx = nxt[0] if forward else nxt[-1]
            self.cx += 1  # just past it: Backspace takes it out

    def exit_mask(self) -> None:
        """Done: the quote shows masked (or whole, if all of it shows). The
        whole edit is one step to undo."""
        p = self.flow_at(self.cy, self.cx)
        while len(self.medit.keys) > 1:
            self.mask_out()
        self.save_mask()
        own = self.medit.flow["own"]
        top = next((loc for key, loc in reversed(own[:p + 1]) if key == ()), 0)
        qid, shown = self.medit.qid, any(shown_in(self.medit.mask, len(own)))
        del self.undo[self.medit.start:]
        self.medit = None
        self.refresh_library()
        f = self.stack[-1]
        stored = self.seen_line(f.lines[f.anchor], len(self.stack) - 1)[1]  # as it's seen here
        target = block_draft(self.library, self.cur_id)
        if stored is None:
            self.vmode = None
            self.load_text(target)
            self.saved = self.snapshot()
            self.place_at(min(top, len(target)))
        else:
            self.load_view(qid, stored, None, clear=False)
            self.place_at(store.draft_to_view(target, stored, top))
        self.message = "" if shown else "nothing shows · ^Z to undo"

    def mask_key(self, key) -> bool:
        """A key while masking; True when it's dealt with here."""
        act = keys.bind(key, "mask")
        if act == "done":
            self.exit_mask()
            return True
        if act in ("open_bracket", "close_bracket"):
            self.bracket("[" if act == "open_bracket" else "]")
            return True
        if act in ("next_bracket", "prev_bracket"):
            self.jump(act == "next_bracket")
            return True
        if act in ("backspace", "delete") and self.selection() is None:
            col = self.cx - 1 if act == "backspace" else self.cx
            line = self.lines[self.cy]
            if 0 <= col < len(line) and line[col] in (OPEN, CLOSE):
                self.unbracket_at(col)
                return True
        if act == "palette":
            self.message = "masking · esc when done"
            return True
        if act is not None and (len(act) == 1 or act in TEXT_EDITS):
            self.message = NO_TYPING
            return True
        return False

    def show_all(self) -> None:
        """Remove mask: the quote selected, or the one the cursor's in, shows all of it again."""
        qid = self.quote_here()[1]
        inside = self.vmode is not None and self.vmode.qid == qid  # editing its view: the buffer changes too
        if inside:
            if self.dirty():
                self.save()
            at = store.view_to_draft(block_draft(self.library, self.cur_id), self.view_mask(),
                                     self.offset_at(self.cy, self.cx))
        try:
            h, record = store.set_quote_mask(qid, None, None, inner=True)
        except store.StoreError as e:
            self.message = str(e)
            return
        self.base.update(h)
        self.step(record)
        self.refresh_library()
        if inside:  # what it shows now (all of it, unless a quote it's seen through hides some)
            target, mask = block_draft(self.library, self.cur_id), self.view_mask()
            if mask is None:
                self.vmode = None
                self.load_text(target)
                self.saved = self.snapshot()
                self.place_at(at)
            else:
                self.load_view(qid, mask, None, clear=False)
                self.place_at(store.draft_to_view(target, mask, at))
