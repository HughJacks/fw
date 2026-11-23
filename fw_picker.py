"""fw_picker — the search list home, Quote a block and the kinds picker share,
in the terminal (its ranking is fw_search's); and home's garden."""

from fw_screen import draw_box
from fw_search import (MEANING_PER, NEW, PROPOSE, Search, blocks_inside, fuse,  # noqa: F401 (the terminal's names for them)
                       new_kind_label, new_label)


class Picker(Search):
    """The terminal's search list (fw_search.Search, ranked there): the
    selection, the keys and the drawing. → on an entry with blocks `inside`
    lists them all under it, ← hides them again (`shown`); the selection
    follows the first result until you move it yourself."""

    def __init__(self, library: dict, refs: list, pinned=(), inside=None, label=None, guesses=None, applied=()):
        super().__init__(library, refs, pinned, inside, label, guesses, applied)
        self.sel = 0
        self.moved = False  # the selection was moved with the arrows (else it follows the first result)
        self.footer = None  # key -> a dim line under the rows, about the selected one (or "")
        self.blue = 0  # the attr a kind's row is drawn with (the caller's Ink.blue)

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
    order (recent and resurfacing mixed first, then the rest; not labelled:
    the user sees it their own way), with "+ new pericope" (and a proposed
    kind, if any) first. Each card: its title, when it was made and changed,
    what last happened to it, and the start of what it says. Arrows move over
    the grid; Enter picks; typing anything hands over to the search
    (`Picker`), which Backspace with nothing typed leaves again. Ctrl+G turns
    the grid into a list drawn as the search's is (a title a row, its date
    and words on the right), in the garden's order, and back."""

    CARD_W, CARD_H = 34, 7

    def __init__(self, cards: list, info, pinned=(), notes=None, faint=(), right=None):
        self.cards = [k for k, _ in pinned] + [k for k, _ in cards]  # keys, in order
        self.why = {}                   # pinned key -> a word on its card's top edge ("proposed")
        self.right = right or (lambda key: "")  # entry -> its row's right side in the list (date, words)
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
                why, lines = "", [dates, action] + wrap_text(preview, inner, 2)
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
        """The cards as the search draws its list (draw_box): a title a row, its date and words on the right."""
        from fw_screen import draw_box
        self.cols = 1
        def row(key):
            if key in self.pinned:  # (a proposed kind: dim, with how many)
                notes = self.notes.get(key, [])
                return (key, self.pinned[key] + (f" · {notes[0]}" if notes else ""), "", *((True,) if key in self.faint else ()))
            return (key, self.info(key)[0], self.right(key))
        rows = [row(k) for k in self.cards]
        first = max(0, self.sel - max_rows + 1)
        notes = self.notes.get(self.selected(), [])[1:]
        footer = " ".join(n.strip() for n in notes)
        return draw_box(scr, y0, x0, bw, prompt, "", rows[first:first + max_rows], self.sel, first, footer,
                        tint=lambda key: self.blue if key in self.kinds else 0)


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
