"""fw_picker — the search list home, Quote a block and the kinds picker share."""

from fw_block import children, families, home_of, is_applied, kind_ids, kind_named, of_kind, quoted
from fw_screen import draw_box

NEW = "+new"        # the "+ new pericope" row, pinned at the top of home and the quote search
PROPOSE = "+propose"  # home's row offering a kind a model proposes (fw_block.open_proposals), pinned under it


def new_label(query: str) -> str:
    return f"+ new pericope “{query}”" if query else "+ new pericope"


def new_kind_label(query: str) -> str:
    return f"+ new kind “{query}”" if query else "+ new kind"


def blocks_inside(library: dict, refs: list) -> dict:
    """The blocks inside each of `refs` a search can find (not quotes), in
    order, with how deep: {entry: [(block, depth), …]}."""
    def walk(i, d, seen):
        for k in children(library.get(i)):
            if k in library and k not in seen and not quoted(library[k]):
                yield k, d
                yield from walk(k, d + 1, seen | {k})
    return {r: list(walk(r, 1, {r})) for r in refs}


class Picker:
    """A search list over entries, the same wherever one is picked (home, the
    quote search, Link to an entry): newest first, and typing filters by
    title (or the start of an id). `pinned` rows, (key, label(query)), sit
    above the results. `inside` ({entry: [(block, depth), …]}, the blocks in
    each, in order) makes it a search over blocks: it offers those whose
    title has what's typed, indented under their entry (and the entry with
    them, if it didn't match itself); → on an entry with blocks `inside`
    lists them all under it, ← hides them again (`shown`). And with what's
    typed, each match brings its kin, dim: the rest of its paraphrase family
    right under it (≈, the same thing said another way), and, below every
    match, the places that quote it (a row per quote, whose key is the quote
    block; `source` turns it into what it quotes). A kind's row is drawn
    blue (`blue`), and in a search over blocks, typing a
    kind's name puts that kind first, the blocks of that kind under it, then
    the blocks a model guesses are (`guesses`, fw_block.guessed's), dim
    (kind_first). The selection follows the
    first result until you move it yourself."""

    def __init__(self, library: dict, refs: list, pinned=(), inside=None, label=None, guesses=None, applied=()):
        self.library, self.refs, self.pinned = library, refs, list(pinned)
        self.guesses = guesses or {}  # {block id: {kind id: p}}: a model's guesses that count
        self.applied = set(applied)    # the learned kinds (fw_block.learned): with blocks inside pericopes, guesses applied (is_applied), listed as said, not dim
        self.label = label  # key -> (left, right) for its row, instead of its title and date (filtered by left)
        self.inside = inside or {}
        self.related = inside is not None  # a search over blocks: kin rows too
        self.query, self.sel = "", 0
        self.moved = False  # the selection was moved with the arrows (else it follows the first result)
        self.footer = None  # key -> a dim line under the rows, about the selected one (or "")
        self.shown = set()  # the entries whose blocks are listed under them (→), whatever is typed
        self.where = {k: e for e, ks in self.inside.items() for k, _ in ks}  # block -> its entry
        self.kinds = set(kind_ids(library))
        self.blue = 0  # the attr a kind's row is drawn with (the caller's Ink.blue)
        if self.related:
            blocks = {i: e["block"] for i, e in library.items()}
            self.family = families(blocks)
            self.quotes = {}  # block -> [(quote block, the entry it's in)] in the places listed
            for i, b in blocks.items():
                q = quoted(b)
                if q and q[0] in library:
                    home = home_of(blocks, i)[0]
                    if home in set(refs):
                        self.quotes.setdefault(q[0], []).append((i, home))

    def rows(self) -> list:
        """(key, title, date and words[, dim]) per row, pinned rows first."""
        pinned = [(key, label(self.query), "", *dim) for key, label, *dim in self.pinned]  # (a third item: drawn dim)
        q = self.query.lower()
        if self.label:
            return pinned + [(r, *self.label(r)) for r in self.refs if q in self.label(r)[0].lower()]
        title = lambda r: self.library[r]["title"]
        first = self.kind_first() if self.related else []
        listed = {r[0] for r in first}
        order = [r for r in self.refs if (q in title(r).lower() or r.startswith(q)) and r not in listed]
        hits = {e: [(k, d) for k, d in self.inside.get(e, [])
                    if (e in self.shown or (q and q in title(k).lower())) and k not in listed]
                for e in self.refs}
        order += [e for e in self.refs if hits.get(e) and e not in order]  # (the entries of blocks that matched)
        tops = set(self.refs)
        def row(r, shown, at=None, dim=False):
            at = at or r
            right = f"{at[4:6]}/{at[6:8]}  {self.library[at].get('words', 0)}w"
            return (r, shown, right, True) if dim else (r, shown, right)
        placed, found = set(), []  # family members listed so far; the matches, in order
        def kin(k, indent):  # a match: the rest of its paraphrase family, under it
            if not (self.related and q and (q in title(k).lower() or k.startswith(q))) or k in found:
                return []
            found.append(k)
            if k in placed or k not in self.family:
                return []
            placed.update(self.family[k])
            return [row(s, indent + "≈ " + title(s), dim=True) for s in self.family[k]
                    if s != k and (s in tops or s in self.where)]
        out = list(first)
        for r in order:
            out += [row(r, title(r))] + kin(r, "  ")
            for k, d in hits.get(r, []):
                out += [row(k, "  " * d + "· " + title(k))] + kin(k, "  " * (d + 1))
        out += [row(x, f"  “{title(k)}” quoted in {title(home)}", home, dim=True)
                for k in found for x, home in self.quotes.get(k, [])]  # below every match
        return pinned + out

    def kind_first(self) -> list:
        """With a kind's name typed (case aside): its row, then a row for
        each block of that kind (in the places listed), oldest first, then,
        each block a model guesses is one (oldest first too): those applied
        (fw_block.is_applied: a learned kind's, or inside a pericope) as the
        rest, any other dim."""
        kid = kind_named(self.library, self.query) if self.query.strip() else None
        if kid is None or kid not in self.refs:
            return []
        blocks = {i: e["block"] for i, e in self.library.items()}
        right = lambda r: f"{r[4:6]}/{r[6:8]}  {self.library[r].get('words', 0)}w"
        title = lambda r: self.library[r]["title"]
        here = lambda k: k in self.refs or k in self.where
        said = [k for k in of_kind(blocks, kid) if here(k)]
        guessed = [k for k in of_kind(blocks, kid, self.guesses) if here(k) and k not in said]
        return ([(kid, title(kid), right(kid))] + [(k, "  · " + title(k), right(k)) for k in said]
                + [(k, "  · " + title(k), right(k)) if is_applied(self.library, k, kid, self.applied) else (k, "  · " + title(k), right(k), True)
                   for k in guessed])

    def source(self, key: str) -> str:
        """What a row stands for: on a place that quotes a match, the match."""
        q = quoted(self.library.get(key))
        return q[0] if q else key

    def home(self, key: str) -> str | None:
        """The entry whose blocks `inside` hold `key` (None for an entry)."""
        return self.where.get(key)

    def first_result(self) -> int:
        """Where the selection goes as you type: the best result, else a pinned row."""
        return len(self.pinned) if len(self.rows()) > len(self.pinned) else 0

    def key(self, act: str | None):
        """Apply one action (bound in the "picker" context). Returns ("pick",
        key) or ("masked", key) for Shift+Enter, "cancel", "back" (Backspace
        with nothing typed), or None to carry on."""
        rows = self.rows()
        if act == "cancel":
            return "cancel"
        if act == "backspace":
            if not self.query:
                return "back"
            self.query = self.query[:-1]
            self.sel, self.moved = self.first_result() if self.query else 0, False
        elif act in ("up", "down"):
            self.sel = min(max(self.sel + (1 if act == "down" else -1), 0), max(len(rows) - 1, 0))
            self.moved = True
        elif act in ("show_blocks", "hide_blocks") and rows:
            key = rows[self.sel][0]
            entry = self.home(key) or key
            if act == "show_blocks" and self.inside.get(entry) and entry == key:
                self.shown.add(entry)
            elif act == "hide_blocks" and entry in self.shown:
                self.shown.discard(entry)
                self.sel = next(n for n, r in enumerate(self.rows()) if r[0] == entry and len(r) == 3)  # back on the entry
            self.moved = True
        elif act in ("pick", "pick_masked"):
            return ("pick" if act == "pick" else "masked", rows[self.sel][0]) if rows else None
        elif act is not None and len(act) == 1:
            self.query = self.query + act
            self.sel, self.moved = self.first_result(), False
        return None

    def height(self, max_rows: int) -> int:
        extra = 1 if self.footer else 0  # (room for the footer line)
        return (min(len(self.rows()), max_rows) + 3 if self.rows() else 4) + extra

    def draw(self, scr, y0: int, x0: int, bw: int, max_rows: int, prompt: str) -> tuple[int, int]:
        rows = self.rows()
        first = max(0, self.sel - max_rows + 1)
        footer = self.footer(rows[self.sel][0]) if self.footer and rows else ""
        return draw_box(scr, y0, x0, bw, prompt + self.query, "", rows[first:first + max_rows], self.sel, first, footer,
                        tint=lambda key: self.blue if key in self.kinds else 0)


class Garden:
    """Home as a garden: a grid of cards, one per entry, in fw_block.garden's
    order (recent, then resurfacing, then the rest), with "+ new pericope"
    (and a proposed kind, if any) first. Each card: its title, why it's here,
    when it was made and changed, what last happened to it, and the start of
    what it says. Arrows move over the grid; Enter picks; typing anything
    hands over to the search (`Picker`), which Backspace with nothing typed
    leaves again. Ctrl+G turns the grid into a list (a card a row: title,
    why, what last happened, dates) and back."""

    CARD_W, CARD_H = 34, 7

    def __init__(self, cards: list, info, pinned=(), notes=None, faint=()):
        self.cards = [k for k, _ in pinned] + [k for k, _ in cards]  # keys, in order
        self.why = dict(cards)          # entry -> "recent" | "resurfacing" | ""
        self.pinned = dict(pinned)      # key -> its label (a pinned card)
        self.info = info                # entry -> (title, dates, action, preview)
        self.notes = notes or {}        # pinned key -> the lines under its label (a proposed kind: what Enter and ^D do)
        self.faint = set(faint)         # pinned keys drawn dim (a proposed kind: only an offer)
        self.sel = len(pinned) if len(self.cards) > len(pinned) else 0
        self.cols, self.top = 1, 0      # set as it's drawn
        self.kinds, self.blue = set(), 0  # the kinds among the cards, and the attr their titles are drawn with
        self.grid = True                # cards in a grid, or a list (a row each): Ctrl+G

    def selected(self) -> str | None:
        return self.cards[self.sel] if self.cards else None

    def key(self, act: str | None):
        """("pick", key), ("search", typed), "cancel", or None to carry on."""
        if act == "cancel":
            return "cancel"
        if act in ("pick", "pick_masked") and self.cards:
            return ("pick", self.cards[self.sel])
        if act == "toggle_view":
            self.grid, self.top = not self.grid, 0
            return None
        step = {"left": -1, "hide_blocks": -1, "right": 1, "show_blocks": 1,
                "up": -self.cols, "down": self.cols}.get(act)
        if step and self.cards:
            self.sel = min(max(self.sel + step, 0), len(self.cards) - 1)  # off the top: the first card (+ new)
        elif act is not None and len(act) == 1 and act.isprintable():
            return ("search", act)
        return None

    def draw(self, scr, y0: int, x0: int, bw: int, max_rows: int, prompt: str, ink=None) -> tuple[int, int]:
        if not self.grid:
            return self.draw_list(scr, y0, x0, bw, max_rows, prompt)
        import curses
        self.cols = max(1, (bw + 1) // (self.CARD_W - 3))  # cards of about CARD_W, as many as fit
        cw = min((bw - (self.cols - 1)) // self.cols, bw)
        rows_fit = max(1, (max_rows + 2) // self.CARD_H)
        row = self.sel // self.cols
        if row < self.top:
            self.top = row
        elif row >= self.top + rows_fit:
            self.top = row - rows_fit + 1
        from fw_screen import put, swidth
        put(scr, y0, x0, (prompt + "type to search")[:bw], curses.A_DIM)
        for n, key in enumerate(self.cards[self.top * self.cols:(self.top + rows_fit) * self.cols]):
            i = self.top * self.cols + n
            y, x = y0 + 2 + (n // self.cols) * self.CARD_H, x0 + (n % self.cols) * (cw + 1)
            on = i == self.sel
            edge = curses.A_BOLD if on else curses.A_DIM
            inner = cw - 4
            if key in self.pinned:
                title, why, lines = self.pinned[key], self.why.get(key, ""), self.notes.get(key, [])
            else:
                title, dates, action, preview = self.info(key)
                why, lines = self.why.get(key, ""), [dates, action] + wrap_text(preview, inner, 2)
            label = f" {why} " if why else ""
            put(scr, y, x, "┌" + label + "─" * max(cw - 2 - len(label), 0) + "┐", edge)
            put(scr, y + 1, x, "│ ", edge)
            put(scr, y + 1, x + 2, clip(title, inner).ljust(inner),
                (curses.A_REVERSE if on else curses.A_DIM if key in self.faint else curses.A_BOLD)
                | (self.blue if key in self.kinds else 0))
            put(scr, y + 1, x + 2 + inner, " │", edge)
            for k in range(self.CARD_H - 3):
                text = lines[k] if k < len(lines) else ""
                attr = curses.A_DIM if k < 2 or key in self.pinned else 0
                put(scr, y + 2 + k, x, "│ ", edge)
                put(scr, y + 2 + k, x + 2, clip(text, inner).ljust(inner), attr)
                put(scr, y + 2 + k, x + 2 + inner, " │", edge)
            put(scr, y + self.CARD_H - 1, x, "└" + "─" * (cw - 2) + "┘", edge)
        return y0, x0 + swidth(prompt)


    def draw_list(self, scr, y0: int, x0: int, bw: int, max_rows: int, prompt: str) -> tuple[int, int]:
        """The cards as a list, a row each: title, why it's here, what last happened, dates."""
        import curses
        from fw_screen import put, swidth
        self.cols = 1
        fit = max(1, max_rows - 1)
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + fit:
            self.top = self.sel - fit + 1
        put(scr, y0, x0, (prompt + "type to search")[:bw], curses.A_DIM)
        tw = max(min(40, bw // 2), 10)
        for n, key in enumerate(self.cards[self.top:self.top + fit]):
            i, y = self.top + n, y0 + 2 + n
            on = i == self.sel
            if key in self.pinned:
                title, rest = self.pinned[key], " · ".join(self.notes.get(key, [])[:1])
                faint = key in self.faint
            else:
                title, dates, action, _ = self.info(key)
                rest, faint = "  ".join(x for x in (self.why.get(key, "").ljust(11), action, dates) if x), False
            put(scr, y, x0, clip(title, tw).ljust(tw), curses.A_REVERSE if on else
                curses.A_DIM if faint else curses.A_BOLD | (self.blue if key in self.kinds else 0))
            put(scr, y, x0 + tw + 2, clip(rest, max(bw - tw - 2, 0)), curses.A_DIM)
        return y0, x0 + swidth(prompt)


def clip(text: str, width: int) -> str:
    from fw_screen import swidth
    out = ""
    for ch in text:
        if swidth(out + ch) > width:
            return out[:-1] + "…" if out else ""
        out += ch
    return out


def wrap_text(text: str, width: int, lines: int) -> list:
    """The first `lines` lines of `text` (whitespace folded), wrapped at words."""
    words, out, line = " ".join(text.split()).split(" "), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
            if len(out) == lines:
                out[-1] = clip(out[-1] + " …", width) if len(out[-1]) + 2 > width else out[-1] + " …"
                return out
        else:
            line = f"{line} {w}" if line else w
    return out + ([line] if line and len(out) < lines else [])
