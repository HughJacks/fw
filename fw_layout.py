"""fw_layout — where everything goes on screen, and drawing it: part of the
editor (a mixin of fw_edit.Editor, whose state it reads).

The layout is a list of rows (`Editor.rows`), one per screen line of text,
each a Row: a stretch of a buffer line (the block being edited), or
something Drawn (text of the blocks around it, a quote's text, a box's top
or bottom, a note). Every block is in a box, at every depth (`box_plan`): a
block of text's faint, a quote's red, and a block with a quote nested in it
(a container) a faint box with its own blocks boxed inside it, a level in.
All text lines up at one column, past room for MAX_DEPTH boxes; a block with
no room left for its box is unboxed, a dim · before its first line (`dots`).
`frames` says which quotes' boxes each row is in, `walls` every box it's in.
Masking draws through fw_mask_ui (rows of kind "mask").

A quote of a kind (what a block can be: a poem) is boxed blue, not red,
muted at rest and bright while selected or edited in, "kind: poem" on its
top line (`kind_boxes`).

An image (a block that is one picture) has a box like a quote's, faint at
rest, with blank rows inside it that the terminal draws the picture over
after curses has drawn the screen (`pictures`; Editor.show_pictures).

A locked quote (no writing through it, fw_block.locked_by) has a ⊘ first on
its top line (LOCK_MARK), and what shows through it is drawn dim, at every
depth: the text of the quotes inside it, and its buffer while you're in it.

A hyperlink (a span of a block of text pointing at an entry) is drawn red
and underlined, with an ↗ after it that isn't in the text: rows wrap, and
the cursor and clicks count columns, with it in (`wrap_links`, `link_x`).

What doesn't need the editor is a plain function, below; the mixin lays out
and draws from its state.
"""

import curses
from typing import NamedTuple

import fw_store as store
from fw_screen import TAB_WIDTH, cwidth, put, swidth, wrap
import fw_image
from fw_store import (CLOSE, ELLIPSIS, IMAGE_RE, MARKS, MAX_DEPTH, OPEN, QUOTE_RE, atom_id, block_draft, chain, image_line,
                      parse_draft, parse_nest)

THIN, HEAVY = "┌┐└┘─│", "┏┓┗┛━┃"  # a box; a selected quote's edge at the end you're on is heavy
ARROW = "↗"  # after a hyperlink
SHOW = {ELLIPSIS: "…", CLOSE: "›", OPEN: "‹"}  # a mask's marks, as they're drawn
EDGES = ("top", "bottom")
LOCK_MARK = "⊘"  # first on a locked quote's top line (one column wide)
PICTURE_ROWS = 16  # the most rows a picture takes (its width shrinks to keep its shape)


class Drawn(NamedTuple):
    """What a row that isn't buffer text shows."""
    depth: int          # how many quotes deep (0: a box of the entry's own text)
    text: str           # (a box's top: its label)
    kind: str           # "text"; "note" (dim); "top", "bottom" (a box's edge); "mask" (being masked); "image" (under a picture)
    codes: tuple = ()   # kind "mask": how each character is drawn (fw_mask_ui.render)
    plain: bool = False  # an edge of a faint box (a block of text's, a container's): the cursor goes past it


class Row(NamedTuple):
    """One screen line of text."""
    line: int | None    # the buffer line it's a stretch of (None: it's drawn, not the buffer)
    start: int          # the stretch
    end: int
    drawn: Drawn | None  # what it shows, when it isn't buffer text
    depth: int


# --- pure: rows and geometry ---------------------------------------------------

PEEK_ROWS = 8  # Show its source: how many rows of it at most


def edge(depth: int, kind: str, label: str = "", plain: bool = False) -> Drawn:
    return Drawn(depth, label, kind, (), plain)


def drawn(depth: int, line: str, width: int, kind: str = "text", codes=None) -> list:
    """A line of text, wrapped to `width`, as drawn rows' contents."""
    return [Drawn(depth, line[s:e], kind, tuple(codes[s:e]) if codes is not None else ())
            for s, e in wrap(line, width)]


def is_edge(d: Drawn | None) -> bool:
    return d is not None and d.kind in EDGES


def is_gap(row: Row) -> bool:
    """A faint box's top or bottom (or the entry's own text, drawn): the cursor goes past it."""
    return row.drawn is not None and (row.drawn.depth == 0 or row.drawn.plain)


def past_gaps(rows: list, t: int, step: int) -> int:
    """The first row from `t`, going by `step` (or back, at the end), that isn't a gap."""
    for s in (step, -step):
        r = t
        while 0 <= r < len(rows) and is_gap(rows[r]):
            r += s
        if 0 <= r < len(rows):
            return r
    return t


def text_width(cols: int, gutter: int) -> int:
    """Columns for text: inside room for MAX_DEPTH nested boxes, a column
    for each side, and a space either side of the text, whatever it's in,
    so all text lines up (and 1 spare column for the cursor)."""
    return max(cols - gutter - 2 * MAX_DEPTH - 3, 1)


def paths_of(lines: list, bids: list, nest: dict) -> list:
    """For each line of a buffer, the containers it's in, outermost first
    (by `nest`, fw_draft.parse_nest): a block of text's, or a quote's."""
    key = lambda line, b: atom_id(line) if b is None else b
    return [chain(nest, key(line, b))[::-1] for line, b in zip(lines, bids)]


def block_units(bids: list, paths: list) -> list:
    """The blocks a buffer shows as numbered boxes, as (first line, last
    line): each block of text, each quote, and each container with all it
    holds (`paths`: the containers each line is in, outermost first)."""
    box = lambda li: paths[li][0] if paths[li] else bids[li]
    starts = [li for li in range(len(bids))
              if li == 0 or (bids[li] is None and not paths[li]) or box(li) != box(li - 1)]
    return list(zip(starts, [s - 1 for s in starts[1:]] + [len(bids) - 1]))


class Plan(NamedTuple):
    """How a buffer line is boxed (box_plan)."""
    opens: tuple  # the depths of the faint boxes that start before it, outermost first
    closes: int   # how many of them end after it
    depth: int    # a quote's box depth, on this line
    dot: bool     # the first line of a block with no room left for its box


def many_blocks(bids: list) -> bool:
    """More than one block of text, or a quote: what's boxed block by block
    (a quote of one block of text shows it in the quote's box alone)."""
    return None in bids or len(set(bids)) > 1


def box_plan(bids: list, paths: list, depth: int, boxed: bool, bare=None) -> list:
    """How the blocks of a buffer `depth` boxes in are boxed, a Plan per line:
    each block of text in a faint box, and each container (`paths`, the
    containers each line is in) a faint box around its blocks, a level in,
    at every depth while there's room (MAX_DEPTH); with none left a block is
    unboxed and dotted. Nothing is boxed unless `boxed`, nor a block of only
    lines that are `bare` (a lone …)."""
    n = len(bids)
    paths = paths if boxed else [()] * n
    room = lambda level: depth + level + 1 <= MAX_DEPTH  # a box for the container `level` deep in
    shared = lambda a, b: next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    run_end = lambda li: bids[li] is None or li + 1 == n or bids[li + 1] != bids[li]
    plans, boxed_run = [], False
    for li in range(n):
        path, before = paths[li], paths[li - 1] if li else ()
        after = paths[li + 1] if li + 1 < n else ()
        opens = [depth + k + 1 for k in range(shared(before, path), len(path)) if room(k)]
        closes = sum(room(k) for k in range(shared(path, after), len(path)))
        inner = depth + sum(room(k) for k in range(len(path)))
        dot = False
        if bids[li] is not None and (li == 0 or bids[li - 1] != bids[li]):  # a block of text starts
            j = li
            while not run_end(j):
                j += 1
            boxed_run = boxed and not (bare and all(bare[li:j + 1])) and inner < MAX_DEPTH
            dot = boxed and not boxed_run and not (bare and all(bare[li:j + 1]))
            if boxed_run:
                opens.append(inner + 1)
        if bids[li] is not None and run_end(li) and boxed_run:
            closes += 1
        plans.append(Plan(tuple(opens), closes, inner + 1, dot))
    return plans


def text_column(gutter: int) -> int:
    """Screen column where text starts, on every row: past the room for MAX_DEPTH boxes."""
    return gutter + MAX_DEPTH + 1


def link_ends(spans: list) -> dict:
    """Where a line's hyperlinks end: {end: the mark after it}."""
    return {e: ARROW for s, e, *_ in spans if e > s}


def link_columns(spans: list) -> set:
    """The columns of a line inside its hyperlinks."""
    return {c for s, e, *_ in spans for c in range(s, e)}


def link_x(line: str, start: int, col: int, ends: dict) -> int:
    """Screen columns from `start` to `col` of `line`, an ↗ counted after each link end."""
    return swidth(line[start:col]) + sum(1 for e in ends if start < e <= col)


def wrap_links(line: str, width: int, ends: dict) -> list:
    """`line` wrapped to `width` with its mark after each link end in `ends`, as
    (start, end) offsets into `line` itself."""
    if not ends:
        return wrap(line, width)
    shown, back = "", []  # the line as drawn, and each of its characters' offset in `line`
    for i, ch in enumerate(line):
        shown, back = shown + ch, back + [i]
        if i + 1 in ends:
            shown, back = shown + ends[i + 1], back + [i + 1]
    back.append(len(line))
    return [(back[s], back[e] if e < len(back) else len(line)) for s, e in wrap(shown, width)]


def linked(line: str, spans: list) -> tuple:
    """A line as drawn, its hyperlinks marked: (the text with a mark after
    each, a code per character: "l" in a link, "a" its arrow, " " else)."""
    ends, inside = link_ends(spans), link_columns(spans)
    text, codes = "", ""
    for i, ch in enumerate(line):
        text, codes = text + ch, codes + ("l" if i in inside else " ")
        if i + 1 in ends:
            text, codes = text + ends[i + 1], codes + "a"
    return text, codes


def box_edge(width: int, kind: str, heavy: bool) -> str:
    """A box's top or bottom, `width` wide."""
    c = HEAVY if heavy else THIN
    ends = c[0:2] if kind == "top" else c[2:4]
    return ends[0] + c[4] * max(width - 2, 0) + ends[1]


def fit(label: str, room: int) -> str:
    """`label` in `room` columns, cut with … if it's longer."""
    return label if swidth(label) <= room else label[:room - 1] + "…"


def masking_cells(text: str, codes, red: int, sel_cols=()) -> list:
    """(char, attr) for a row of text being masked, from its codes
    (fw_mask_ui.render): hidden parts dim, a bracket you typed `red` and
    bold, an implied one dim; a … left to `put_runs`."""
    cells = []
    for c, (ch, code) in enumerate(zip(text, codes)):
        if code in "ocOC":
            attr = red | (curses.A_DIM if code in "OC" else curses.A_BOLD)
        else:
            attr = 0 if code == "s" or ch == ELLIPSIS else curses.A_DIM
        cells.append((ch, attr | (curses.A_REVERSE if c in sel_cols else 0)))
    return cells


def put_runs(scr, y: int, x: int, cells: list, red: int, mark: int) -> None:
    """Draw (char, attr) cells from column x, a mask's marks as …, ›, ‹. Of
    those with nothing else to say, a … is `red` (0: dim) and a bracket `mark`, bold."""
    run, attr = "", None
    for ch, a in cells:
        shown = SHOW.get(ch, ch).replace("\t", " " * TAB_WIDTH)
        if ch == ELLIPSIS and a == 0:
            a = red or curses.A_DIM
        elif ch in (OPEN, CLOSE) and a == 0:
            a = mark | curses.A_BOLD
        if a != attr and run:
            put(scr, y, x, run, attr)
            x += swidth(run)
            run = ""
        run, attr = run + shown, a
    if run:
        put(scr, y, x, run, attr)


# --- the mixin ------------------------------------------------------------------

class Layout:
    def ensure_layout(self) -> None:
        if not self.stale:
            return
        f = self.stack[0] if self.stack else None
        lines, bids, nest = (f.lines, f.bids, f.nest) if f else (self.lines, self.bids, self.nest)
        # the gutter numbers the entry's blocks, not lines: each quote, each
        # block of text, and each container (all it holds in one box)
        self.paths = paths_of(lines, bids, nest)  # the containers each line of the entry is in
        units = block_units(bids, self.paths)
        self.block_no = {s: n for n, (s, _) in enumerate(units, start=1)}
        self.gutter = len(str(len(units))) + 1
        self.rows, self.first_row, self.row_no = [], [], {}
        self.spans = []  # (first row, last row, depth) of every quote on screen, its box included
        self.plains = []  # (first row, last row, depth) of every faint box (a block of text's, a container's)
        self.para_tops = set()  # the rows a paraphrase's box starts on (its "≈ source" top line)
        self.para_boxes = set()  # the faint boxes that are paraphrases' (indexes into plains): drawn red
        self.dots = set()  # the rows a block with no room for its box starts on
        self.unit_rows = []  # [first row, last row] of each block of the buffer being edited (fw_blocks), in order
        self.pictures = []  # (first row, columns, rows, file name) of every picture's place
        self.image_boxes = set()  # the spans that are images' boxes, not quotes
        self.kind_boxes = set()  # the spans that are quotes of kinds: blue
        self.emit(0, 0, [self.open_ids()[0]])
        self.spans.sort(key=lambda span: span[2])
        self.frames = [[] for _ in self.rows]  # each row's quotes, outermost first (indexes into spans)
        self.walls = [[] for _ in self.rows]  # each row's boxes, outermost first: (depth, "quote" or "plain", its index)
        for n, (first, last, d) in enumerate(self.spans):
            for r in range(first, last + 1):
                self.frames[r].append(n)
                self.walls[r].append((d, "quote", n))
        for n, (first, last, d) in enumerate(self.plains):
            for r in range(first, last + 1):
                self.walls[r].append((d, "plain", n))
        for w in self.walls:
            w.sort(key=lambda wall: wall[0])
        self.qdepth = [len(f) for f in self.frames]  # how many quotes deep each row is
        self.stale = False

    def inner(self) -> int:
        return text_width(self.cols, self.gutter)

    def text_x(self, r: int) -> int:
        return text_column(self.gutter)

    def is_gap(self, r: int) -> bool:
        return is_gap(self.rows[r])

    def past_gaps(self, t: int, step: int) -> int:
        return past_gaps(self.rows, t, step)

    def at_top(self) -> bool:
        """The cursor is on the first row of text on screen."""
        return all(self.is_gap(r) for r in range(self.cursor_row()))

    def emit(self, level: int, depth: int, path: list) -> None:
        """Lay out the block at stack `level` (the one being edited when level
        == len(self.stack)), `depth` boxes in. An open quote is laid out
        exactly like a read-only one (box_plan for both), so nothing moves as
        the cursor goes in or out."""
        active = level == len(self.stack)
        f = None if active else self.stack[level]
        lines, bids, nest = (self.lines, self.bids, self.nest) if active else (f.lines, f.bids, f.nest)
        spans = self.line_links(lines, bids, self.vmode if active else f.vmode)
        if active:
            self.spans_now = spans  # (the cursor's column and clicks count the arrows)
        anchor = None if active else f.anchor
        dim = self.locked(level)  # shown through a locked quote: dim
        width = self.inner()
        masking = self.medit is not None and level >= self.medit.depth  # inside the quote being masked
        key = self.medit.keys[level - self.medit.depth] if masking else None
        drawn_rows = lambda own, ds: [Row(own, 0, 0, d, d.depth) for d in ds]
        paths = self.paths if level == 0 else paths_of(lines, bids, nest)
        path_of = paths if (level == 0 or many_blocks(bids)) else [()] * len(lines)  # (as box_plan boxes them)
        starts = {s for s, _ in block_units(bids, paths)} if active else set()  # (its blocks, for fw_blocks)
        opened = []  # (first row, depth) of the faint boxes open
        plan = box_plan(bids, paths, depth, level == 0 or many_blocks(bids), [line == ELLIPSIS for line in lines])
        for li, (line, p) in enumerate(zip(lines, plan)):
            m = QUOTE_RE.fullmatch(line)
            image = IMAGE_RE.fullmatch(line)
            if level == 0 and li in self.block_no:
                self.row_no[len(self.rows)] = self.block_no[li]
            if li in starts:
                if self.unit_rows:
                    self.unit_rows[-1][1] = len(self.rows) - 1
                self.unit_rows.append([len(self.rows), None])
            for d in p.opens:
                k = d - depth - 1  # (a container's box, k deep in its path; past them, the block of text's own)
                label = self.para_label(path_of[li][k] if k < len(path_of[li]) else bids[li])
                if label:
                    self.para_tops.add(len(self.rows))
                opened.append((len(self.rows), d))
                self.rows.append(Row(None, 0, 0, edge(d, "top", label, plain=True), depth))
                blk = path_of[li][k] if k < len(path_of[li]) else bids[li]
                if label and blk in self.peeking:  # Show its source: its text, dim, at the top inside
                    self.rows += [Row(None, 0, 0, r, depth) for r in self.peek_rows(blk, depth, width)]
            qd = p.depth  # a quote's box depth
            if active:
                self.first_row.append(len(self.rows))
            if p.dot:
                self.dots.add(len(self.rows))
            own = li if active else None
            if image:
                self.rows += drawn_rows(own, self.image_rows(image.group(1), qd, len(self.rows)))
            elif m and li == anchor:  # the quote open below: its block laid out inside its box
                first = len(self.rows)
                label = self.top_label(m.group(1), self.show_of(m.group(2)), m.group(2))
                self.rows.append(Row(None, 0, 0, edge(qd, "top", label), qd))
                self.emit(level + 1, qd, path + [m.group(1)])
                self.rows.append(Row(None, 0, 0, edge(qd, "bottom"), qd))
                self.spans.append((first, len(self.rows) - 1, qd))
                if self.kind_label(m.group(1)):
                    self.kind_boxes.add(self.spans[-1])
            elif m and masking and key + (m.group(2),) in self.medit.flow["segs"]:
                # as it's being masked: all its text, hidden parts dim, the brackets in it
                self.rows += drawn_rows(own, self.masking_rows(key + (m.group(2),), path, qd, len(self.rows)))
            elif m:
                target, mask, show, qinner = self.seen_line(line, level)
                if mask == [] and level > 0:  # a quote inside that shows nothing: no box, a …
                    self.rows.append(Row(own, 0, 0, Drawn(depth, ELLIPSIS, "text"), depth))
                else:
                    self.rows += drawn_rows(own, self.quote_rows(target, path, qd, len(self.rows), mask, show, qinner,
                                                                 m.group(2), dim))
            elif active:
                self.rows += [Row(li, s, e, None, depth) for s, e in wrap_links(line, width, link_ends(spans[li]))]
            elif masking:  # the text around the quote the cursor's gone into, as it's being masked
                self.rows += drawn_rows(None, drawn(depth, line, width, "mask", self.stack[level].meta[li][0]))
            elif spans[li]:
                text, codes = linked(line, spans[li])
                self.rows += drawn_rows(None, drawn(depth, text, width, "note" if dim else "text", codes))
            else:
                self.rows += drawn_rows(None, drawn(depth, line, width, "note" if dim else "text"))
            if active and li == len(lines) - 1:
                self.active_end = len(self.rows) - 1
            self.close_boxes(opened, p.closes, self.rows, lambda d: Row(None, 0, 0, d, depth))
        if active and self.unit_rows:
            self.unit_rows[-1][1] = len(self.rows) - 1

    def kind_label(self, ref) -> str:
        """A kind's top line, "tag: <its name>" (called a tag, 2026-11-24); "" for a block that isn't one."""
        name = store.kind_of(self.library.get(ref, {}).get("block")) if ref else None
        return f"tag: {name}" if name is not None else ""

    def para_label(self, ref) -> str:
        """A paraphrase's top line, "≈ <its source's title>"; "" for a block that isn't one."""
        source = store.paraphrases(self.library.get(ref)) if ref else None
        if not source:
            return ""
        return "≈ " + (self.library[source]["title"] if source in self.library else "(its source is gone)")

    def peek_rows(self, ref: str, depth: int, width: int) -> list:
        """A paraphrase's source, as dim rows the cursor passes (at most
        PEEK_ROWS, then …), a blank row after."""
        source = store.paraphrases(self.library.get(ref))
        blocks = {i: e["block"] for i, e in self.library.items()}
        text = store.shown_text(blocks, source) if source in blocks else "(its source is gone)"
        out = [d._replace(plain=True) for line in text.split("\n") for d in drawn(depth, line, width, "note")]
        if len(out) > PEEK_ROWS:
            out = out[:PEEK_ROWS - 1] + [Drawn(depth, ELLIPSIS, "note", (), True)]
        return out + [Drawn(depth, "", "note", (), True)]

    def guide(self, li: int) -> str:
        """What an empty paraphrase shows dim, line `li` its only line: its
        source's text, as one line ("" for anything else)."""
        bid = self.bids[li]
        if bid is None or self.medit or self.vmode:
            return ""
        top, last = self.block_at(li)
        source = store.paraphrases(self.library.get(bid)) if top == last else None
        if not source or source not in self.library:
            return ""
        blocks = {i: e["block"] for i, e in self.library.items()}
        return " ".join(store.shown_text(blocks, source).split())

    def close_boxes(self, opened: list, n: int, rows: list, row=lambda d: d, base: int = 0) -> None:
        """End the last `n` faint boxes `opened` ((first row, depth) each): their
        bottoms onto `rows` (`row` makes one from its Drawn), which start on row `base`."""
        for _ in range(n):
            first, d = opened.pop()
            rows.append(row(edge(d, "bottom", plain=True)))
            self.plains.append((first, base + len(rows) - 1, d))
            if first in self.para_tops:
                self.para_boxes.add(len(self.plains) - 1)

    @property
    def link_attr(self) -> int:
        return self.ink.red | curses.A_UNDERLINE

    def code_attr(self, code: str, attr: int) -> int:
        """A character's attr from its code (`linked`): a link's red."""
        return self.link_attr if code in "la" else attr

    def col_x(self, li: int, start: int, col: int) -> int:
        """Columns from `start` to `col` of buffer line `li` as drawn (each link's ↗ counted)."""
        return link_x(self.lines[li], start, col, link_ends(self.spans_now[li]))

    def link_here(self):
        """The hyperlink the cursor is in or at the edge of: (start, end, entry id, the stored link), else None."""
        if self.stale:
            self.ensure_layout()
        return next(((s, e, to, link) for s, e, to, link in self.spans_now[self.cy]
                     if s <= self.cx <= e), None)

    def line_links(self, lines: list, bids: list, vmode=None) -> list:
        """Each line's hyperlinks, live: [(start, end, entry id, the stored
        link)], the stored spans moved onto the text as it is in the buffer
        now (none in a masked view, whose text isn't the block's own)."""
        out = [[] for _ in lines]
        if vmode is not None or self.medit is not None:
            return out
        i = 0
        while i < len(lines):
            j, _, spans = self.block_links(lines, bids, i)
            for s, e, to, what in spans:
                at = 0
                for k in range(i, j + 1):
                    if s < at + len(lines[k]) and e > at:
                        out[k].append((max(s, at) - at, min(e, at + len(lines[k])) - at, to, what))
                    at += len(lines[k]) + 1
            i = j + 1
        return out

    def block_links(self, lines: list, bids: list, i: int) -> tuple:
        """The block of text that starts on line `i`: (its last line, its text,
        its hyperlinks live, as (start, end, entry id, the stored link) in that text)."""
        j = i
        while j + 1 < len(lines) and bids[j + 1] == bids[i]:
            j += 1
        b = self.library.get(bids[i], {}).get("block") if bids[i] else None
        text = "\n".join(lines[i:j + 1])
        spans = []
        if b and isinstance(b.get("content"), str) and store.links(b):
            for link, moved in zip(store.links(b), store.move_links(b["content"], text, store.links(b))):
                s, e = moved["at"]
                if s < e and link["to"] in self.library:  # not emptied, nor pointing at an entry that's gone
                    spans.append((s, e, link["to"], link))
        return j, text, spans

    def quote_rows(self, ref: str, path: list, depth: int, base: int, mask=None, show=(), inner=None,
                   qid=None, dim: bool = False) -> list:
        """What quote `qid` of block `ref` shows, `depth` boxes in, as Drawn rows:
        its blocks boxed as an open one's are (box_plan), in its box (its top
        line showing the properties in `show`, and the lock if it's locked);
        `base` is the row it starts on; its text dim if it or a quote around
        it (`dim`) is locked. A block already on `path` (a cycle) or past
        MAX_DEPTH gets a one-line stand-in."""
        dim = dim or store.quote_lock(self.library.get(qid))
        entry = self.library.get(ref)
        if entry is None:
            body = [Drawn(depth, f"missing block {ref}", "note")]
        elif ref in path:
            body = [Drawn(depth, f"↻ {entry['title']}", "note")]
        elif depth > MAX_DEPTH:  # no room for its box: a line in the box around it
            return [Drawn(depth, f"⋯ {entry['title']}", "note")]
        elif mask == [] and store.empties(store.raw_mask((self.library.get(qid) or {}).get("block"))):
            body = [Drawn(depth, "(nothing here now)", "note")]  # all it showed was deleted (its empty places kept)
        else:
            body = self.quote_body(ref, path, depth, base + 1, mask, inner, dim) or [Drawn(depth, "(empty)", "note")]
        label = self.top_label(ref, show, qid)
        rows = [edge(depth, "top", label), *body, edge(depth, "bottom")]
        self.spans.append((base, base + len(rows) - 1, depth))
        if self.kind_label(ref):
            self.kind_boxes.add(self.spans[-1])
        return rows

    def quote_body(self, ref: str, path: list, depth: int, base: int, mask, inner, dim: bool = False) -> list:
        """The rows inside a quote of `ref`'s box (from row `base`), its text dim if `dim` (locked)."""
        lines, bids, nest, quotes = self.quote_lines(ref, mask, inner)
        paths = paths_of(lines, bids, nest)
        plan = box_plan(bids, paths, depth, many_blocks(bids), [line == ELLIPSIS for line in lines])
        body, opened, width = [], [], self.inner()
        lone = Drawn(depth, ELLIPSIS, "text")  # all of a stretch hidden: one … (never two in a row)
        for li, (line, p) in enumerate(zip(lines, plan)):
            for d in p.opens:
                k = d - depth - 1  # (as in emit: a container's box, or the block of text's own)
                label = self.para_label(paths[li][k] if k < len(paths[li]) else bids[li])
                if label:
                    self.para_tops.add(base + len(body))
                opened.append((base + len(body), d))
                body.append(edge(d, "top", label, plain=True))
            if p.dot:
                self.dots.add(base + len(body))
            match quotes.get(li):
                case ("image", iid):
                    body += self.image_rows(iid, p.depth, base + len(body))
                case ("quote", _, [], _, _):  # a quote inside that shows nothing: no box, a …
                    body += [lone] if body[-1:] != [lone] else []
                case ("quote", target, qmask, qshow, qinner):
                    body += self.quote_rows(target, path + [ref], p.depth, base + len(body), qmask, qshow, qinner,
                                            (self.quote_at(line) or (None, None))[1], dim)
                case None if not (line == ELLIPSIS and body[-1:] == [lone]):
                    body += drawn(depth, line, width, "note" if dim else "text")
            self.close_boxes(opened, p.closes, body, base=base)
        return body

    def quote_lines(self, ref: str, mask, inner) -> tuple:
        """What a quote of `ref` (with `mask`) shows, as lines of its draft:
        (lines, bids, nest, {line: its quote as an item, seen through
        `inner`}); live from an editing buffer showing the same thing, so
        every copy on screen follows the typing, else as stored."""
        inner = inner or {}
        f = next((f for f in self.stack if f.id == ref), None)
        lines, bids, nest, vmode = ((self.lines, self.bids, self.nest, self.vmode) if ref == self.cur_id
                                    else (f.lines, f.bids, f.nest, f.vmode) if f else (None,) * 4)
        live = lines is not None and (mask is None) == (vmode is None)
        if not live and store.image_of(self.library.get(ref, {}).get("block")):
            lines, bids, nest = [image_line(ref)], [None], {}  # (a picture, quoted: the picture)
        elif not live:
            draft = block_draft(self.library, ref)
            draft = draft if mask is None else store.view(draft, mask)
            (lines, bids), nest = parse_draft(draft), parse_nest(draft)
        quotes = {}
        for li, line in enumerate(lines):
            q = self.quote_at(line)
            if q and q[1] in self.library and store.quoted(self.library[q[1]]):
                quotes[li] = store.seen_quote(self.library, q[1], inner)
            elif q:
                quotes[li] = ("quote", q[0], q[2], [], inner)
            elif image := IMAGE_RE.fullmatch(line):
                quotes[li] = ("image", image.group(1))
        return lines, bids, nest, quotes

    def image_rows(self, iid: str, depth: int, base: int) -> list:
        """Image block `iid`, `depth` boxes in, as Drawn rows: its box, and
        inside it blank rows for the picture (`pictures`), as many as its
        shape needs at the text's width; or a line saying why there's none.
        `base` is the row it starts on."""
        name = store.image_of(self.library.get(iid, {}).get("block"))
        px = self.picture_size(name) if name else None
        if depth > MAX_DEPTH:
            return [Drawn(depth, "⋯ picture", "note")]
        if px is None:
            body = [Drawn(depth, "▣ missing picture" if name else f"missing block {iid}", "note")]
        elif not self.can_draw_pictures:
            body = [Drawn(depth, f"▣ picture {px[0]}×{px[1]}", "note")]
        else:
            cols, rows = fw_image.rows_for(px, self.inner(), PICTURE_ROWS)
            self.pictures.append((base + 1, cols, rows, name))
            body = [Drawn(depth, "", "image")] * rows
        rows = [edge(depth, "top"), *body, edge(depth, "bottom")]
        self.spans.append((base, base + len(rows) - 1, depth))
        self.image_boxes.add(self.spans[-1])
        return rows

    def picture_size(self, name: str):
        """A picture's (width, height) in pixels (read once), or None if its file's gone."""
        if name not in self.picture_px:
            try:
                self.picture_px[name] = fw_image.size(store.image_file(name).read_bytes())
            except OSError:
                return None
        return self.picture_px[name]

    def top_label(self, ref: str, show, qid=None) -> str:
        """A quote's top line: ⊘ if quote `qid` is locked, then what its
        source `ref` is (a kind, a paraphrase) and the properties in `show`."""
        return self.lock_label(qid, " · ".join(
            x for x in (self.kind_label(ref), self.quote_label(ref, show), self.para_label(ref)) if x))

    def lock_label(self, qid, label: str) -> str:
        """Quote `qid`'s top line `label`, with ⊘ first if it's locked."""
        if store.quote_lock(self.library.get(qid)):
            return f"{LOCK_MARK} {label}" if label else LOCK_MARK
        return label

    def quote_label(self, ref: str, show) -> str:
        """What a quote of `ref` shows in its top line: the properties in `show`."""
        entry = self.library.get(ref)
        if entry is None:
            return ""
        value = {"title": lambda: entry["title"],
                 "created": lambda: store.pretty_time(entry["block"].get("created"), clock=False),
                 "updated": lambda: "updated " + store.pretty_time(entry["block"].get("updated")),
                 "words": lambda: f"{entry['words']} words"}
        return " · ".join(value[k]() for k in show)

    # --- where the cursor is, in rows -----------------------------------------
    def selected_end(self):
        """With a quote or blocks selected whole: (the row of the end you're at, "top" or "bottom"), else None."""
        if self.picked is not None and self.palette is None:
            first, last = self.unit_rows[self.picked.at]
            return (first, "top") if self.picked.edge == "top" else (last, "bottom")
        if self.fedit is not None or self.palette is not None or not self.on_atom():
            return None
        if self.unit_side == "after":
            return self.last_row(self.cy), "bottom"
        return self.first_row[self.cy], "top"

    def next_stop(self):
        """With a quote selected by an arrow: (row, column, character) of where
        one more press in that direction lands inside it (or in the block of
        text selected whole, fw_blocks), else None."""
        if self.picked is not None:
            return self.picked_ghost() if self.palette is None else None
        if self.fedit is not None or self.palette is not None or not self.on_atom() \
                or self.anchor is not None or self.unit_side is None or not self.enterable(self.cy):
            return None
        r = self.first_row[self.cy] + 1 if self.unit_side == "before" else self.last_row(self.cy) - 1
        r = self.past_gaps(r, 1 if self.unit_side == "before" else -1)  # (into a block of text's box)
        if is_edge(self.rows[r].drawn):
            return None  # a quote inside it: that's what gets selected
        text = self.rows[r].drawn.text
        want = self.goal_x if self.goal_x is not None else (0 if self.unit_side == "before" else swidth(text))
        col = x = 0
        while col < len(text) and x + cwidth(text[col]) <= want:
            x += cwidth(text[col])
            col += 1
        # in a masked view the cursor arrives past a leading …, or before a trailing one
        if col == 0 and text[:1] == ELLIPSIS and self.unit_side == "before":
            x, col = cwidth(text[0]), 1
        if col == len(text) and text[-1:] == ELLIPSIS and self.unit_side == "after":
            col -= 1
            x -= cwidth(text[-1])
        ch = text[col] if col < len(text) else " "
        return r, self.text_x(r) + x, SHOW.get(ch, ch)

    def picked_rows(self) -> set:
        """The rows of the blocks selected whole (fw_blocks)."""
        if self.picked is None:
            return set()
        lo, hi = self.picked_span()
        return set(range(self.unit_rows[lo][0], self.unit_rows[hi][1] + 1))

    def picked_boxes(self) -> tuple:
        """The boxes of the blocks selected whole, lit: (quotes, faint boxes),
        as indexes into `spans` and `plains`. The quotes among them (in a
        container too) bright, like one the arrows select; not the boxes
        inside those quotes."""
        rows = self.picked_rows()
        within = lambda first, last: first in rows and last in rows
        quotes = {n for n, (first, last, _) in enumerate(self.spans) if within(first, last)}
        top = {n for n in quotes if not any(m in quotes for m in self.frames[self.spans[n][0]] if m != n)}
        plains = {n for n, (first, last, _) in enumerate(self.plains)
                  if within(first, last) and not any(m in quotes for m in self.frames[first])}
        return top, plains

    def last_row(self, li: int) -> int:
        r = self.first_row[li + 1] - 1 if li + 1 < len(self.lines) else self.active_end
        while self.is_gap(r):  # the boxes between blocks of text
            r -= 1
        return r

    def cursor_row(self) -> int:
        r = self.first_row[self.cy]
        if self.rows[r].drawn is not None:  # on a quote: at its opening mark, or its closing one
            return self.last_row(self.cy) if self.unit_side == "after" else r
        while True:
            row = self.rows[r]
            last = r + 1 >= len(self.rows) or self.rows[r + 1].line != self.cy
            if row.start <= self.cx < row.end or last:
                return r
            r += 1

    # --- drawing ----------------------------------------------------------------
    def draw_rows(self, scr, top: int, sel, end_mark) -> None:
        """Draw the rows of text on screen, from the layout: numbers, boxes,
        and what each row shows (`top`: the screen row they start on)."""
        open_ = lambda level: self.frames[self.first_row[0]][level]  # the quote open at a stack level
        if self.medit:  # masking: only the quote being masked is bright, and the status bar names it
            hot = {open_(self.medit.depth - 1)}
            focus = open_(self.medit.depth - 1)
        else:
            r = self.first_row[self.cy]
            own = self.frames[r][-1] if self.frames[r] else None  # (a stand-in, too deep or a loop, has no box of its own)
            selected = own if self.on_atom() and own is not None and self.spans[own][0] == r else None
            inside = open_(len(self.stack) - 1) if self.stack else None
            hot = {n for n in (selected, inside) if n is not None} | self.picked_boxes()[0]
            focus = selected if selected is not None else inside  # the block the status bar names
        lit, lit_boxes = self.picked_rows(), self.picked_boxes()[1]
        here = self.first_row[self.cy] if self.first_row and not self.medit else -1
        self.para_hot = {n for n in self.para_boxes if self.plains[n][0] <= here <= self.plains[n][1]}
        x = text_column(self.gutter)
        dim = curses.A_DIM if self.locked() else 0  # the buffer, through a locked quote
        for y in range(self.text_h):
            i = self.scroll + y
            if i >= len(self.rows):
                break
            row = self.rows[i]
            if i in self.row_no:  # a quote's number white on red while bright, else muted; a block of text's dim
                number = str(self.row_no[i]).rjust(self.gutter - 1)
                picked = (self.qdepth[i] and row.line is not None and sel and sel[0] <= (row.line, 0) < sel[1]
                          or i in lit)
                if self.qdepth[i] and self.is_image_box(self.frames[i][-1]):  # an image's: as a block of text's
                    attr = curses.A_REVERSE if self.frames[i][-1] in hot else curses.A_DIM
                elif self.qdepth[i] and self.is_kind_box(self.frames[i][-1]):  # a kind's: white on blue, else muted blue
                    attr = (self.ink.blue_tag if self.frames[i][-1] in hot else self.ink.blue_soft) | (
                        curses.A_REVERSE if picked else 0)
                else:
                    attr = ((self.ink.tag if self.frames[i][-1] in hot else self.ink.soft) if self.qdepth[i]
                            else curses.A_DIM) | (curses.A_REVERSE if picked else 0)
                put(scr, top + y, 0, number, attr)
            self.draw_box(scr, top + y, i, hot, end_mark, lit_boxes)
            if i in self.dots:  # a block with no room for its box: a dot before it
                put(scr, top + y, x - 1, "·", curses.A_DIM)
            # a … is red only at the top level of the block the status bar names
            red = self.ink.red if focus is not None and self.frames[i] and self.frames[i][-1] == focus else 0
            d = row.drawn
            if d is not None:
                if d.kind == "mask":
                    put_runs(scr, top + y, x, masking_cells(d.text, d.codes, self.ink.red), red, self.ink.red)
                elif d.kind not in EDGES:  # (an edge is the box's: drawn, label and all)
                    attr = 0 if d.kind == "text" else curses.A_DIM
                    codes = d.codes or " " * len(d.text)
                    put_runs(scr, top + y, x, [(c, self.code_attr(k, attr)) for c, k in zip(d.text, codes)],
                             red, self.ink.red)
                continue
            line, cols = self.lines[row.line], range(row.start, row.end)
            guide = self.guide(row.line) if not line else ""
            if guide:  # a paraphrase not yet written: its source, dim, to write over
                put(scr, top + y, x, fit(guide, max(self.inner() - 1, 1)), curses.A_DIM)
                continue
            picked = [c - row.start for c in cols if sel and sel[0] <= (row.line, c) < sel[1]]
            if self.medit and self.medit.meta[row.line]:  # masking: drawn from the mask
                codes = self.medit.meta[row.line][0][row.start:row.end]
                put_runs(scr, top + y, x, masking_cells(line[row.start:row.end], codes, self.ink.red, picked), red, self.ink.red)
            else:
                spans = self.spans_now[row.line]
                inside, ends = link_columns(spans), link_ends(spans)
                cells = []
                for c in cols:
                    attr = self.char_attr(line[c], c - row.start in picked, red) | dim
                    cells.append((line[c], attr | self.link_attr if c in inside else attr))
                    if c + 1 in ends:
                        cells.append((ends[c + 1], self.link_attr))
                put_runs(scr, top + y, x, cells, red, self.ink.red)

    def is_image_box(self, n: int) -> bool:
        """Span `n` is an image's box, not a quote's."""
        return self.spans[n] in self.image_boxes

    def is_kind_box(self, n: int) -> bool:
        """Span `n` is a quote of a kind: blue."""
        return self.spans[n] in self.kind_boxes

    def char_attr(self, ch: str, picked: bool, red: int) -> int:
        """A buffer character's attr: selected reversed, a mask's mark red (a … dim
        unless it's the status bar's block's own)."""
        attr = curses.A_REVERSE if picked else 0
        if ch == ELLIPSIS and not red:
            return attr | curses.A_DIM
        if ch in MARKS:
            return attr | self.ink.red | curses.A_BOLD
        return attr

    def draw_box(self, scr, y: int, i: int, hot: set, end_mark, lit: set = frozenset()) -> None:
        """Row `i`'s box sides, outermost first, or the top or bottom of its
        innermost box, a column a side: a block of text's faint (bright while
        selected whole, in `lit`), a quote's muted, bright red while selected or
        edited in (a kind's blue, likewise), an image's faint, bright while
        selected; and heavy at the end
        of the selected one you're on."""
        d = self.rows[i].drawn
        para = lambda n: self.ink.red | curses.A_BOLD if n in self.para_hot or n in lit else self.ink.soft
        boxes = [para(n) if kind == "plain" and n in self.para_boxes
                 else (curses.A_BOLD if n in lit else self.ink.faint) if kind == "plain"
                 else (curses.A_BOLD if n in hot else self.ink.faint) if self.is_image_box(n)
                 else (self.ink.blue | curses.A_BOLD if n in hot else self.ink.blue_soft) if self.is_kind_box(n)
                 else (self.ink.red | curses.A_BOLD if n in hot else self.ink.soft) for _, kind, n in self.walls[i]]
        boxes = boxes or [self.ink.faint]
        right = self.cols - 2
        for k, attr in enumerate(boxes):
            lx, rx = self.gutter + k, right - k
            if k == len(boxes) - 1 and is_edge(d):
                put(scr, y, lx, box_edge(rx - lx + 1, d.kind, end_mark == (i, d.kind)), attr)
                room = rx - lx - 4  # "┌─ " … " ─┐"
                if d.kind == "top" and d.depth > 0 and d.text and room > 1:
                    put(scr, y, lx + 2, f" {fit(d.text, room)} ", attr)
            else:
                put(scr, y, lx, THIN[5], attr)
                put(scr, y, rx, THIN[5], attr)
