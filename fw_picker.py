"""fw_picker — the search list home and Quote a block share."""

from fw_block import children, families, home_of, quoted
from fw_screen import draw_box

NEW = "+new"        # the "+ new pericope" row, pinned at the top of home and the quote search


def new_label(query: str) -> str:
    return f"+ new pericope “{query}”" if query else "+ new pericope"


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
    block; `source` turns it into what it quotes). The selection follows the
    first result until you move it yourself."""

    def __init__(self, library: dict, refs: list, pinned=(), inside=None, label=None):
        self.library, self.refs, self.pinned = library, refs, list(pinned)
        self.label = label  # key -> (left, right) for its row, instead of its title and date (filtered by left)
        self.inside = inside or {}
        self.related = inside is not None  # a search over blocks: kin rows too
        self.query, self.sel = "", 0
        self.moved = False  # the selection was moved with the arrows (else it follows the first result)
        self.footer = None  # key -> a dim line under the rows, about the selected one (or "")
        self.shown = set()  # the entries whose blocks are listed under them (→), whatever is typed
        self.where = {k: e for e, ks in self.inside.items() for k, _ in ks}  # block -> its entry
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
        pinned = [(key, label(self.query), "") for key, label in self.pinned]
        q = self.query.lower()
        if self.label:
            return pinned + [(r, *self.label(r)) for r in self.refs if q in self.label(r)[0].lower()]
        title = lambda r: self.library[r]["title"]
        order = [r for r in self.refs if q in title(r).lower() or r.startswith(q)]
        hits = {e: [(k, d) for k, d in self.inside.get(e, []) if e in self.shown or (q and q in title(k).lower())]
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
        out = []
        for r in order:
            out += [row(r, title(r))] + kin(r, "  ")
            for k, d in hits.get(r, []):
                out += [row(k, "  " * d + "· " + title(k))] + kin(k, "  " * (d + 1))
        out += [row(x, f"  “{title(k)}” quoted in {title(home)}", home, dim=True)
                for k in found for x, home in self.quotes.get(k, [])]  # below every match
        return pinned + out

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
        return draw_box(scr, y0, x0, bw, prompt + self.query, "", rows[first:first + max_rows], self.sel, first, footer)
