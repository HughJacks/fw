"""fw_search — the search list, ranked: what home's search, Quote a block,
Link to an entry and the kinds picker list for what's typed (the audit of
2026-11-19: apart from the terminal, so both editors use it and the web
core never imports curses). Pure: standard library and fw_block only."""

from fw_block import alongside, children, families, garden, hits, home_of, is_applied, kind_ids, kind_named, of_kind, pericope_edges, quoted, visited_next

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


MEANING_PER = 2  # blocks found by meaning listed under one pericope, at most (its nearest)


def fuse(*lists: list, k: int = 60) -> list:
    """Ranked lists made one, by reciprocal rank (each item scored by the sum
    of 1 / (k + its rank) in the lists it's in); ties as first listed."""
    score, first = {}, []
    for lst in lists:
        for n, x in enumerate(lst):
            score[x] = score.get(x, 0.0) + 1.0 / (k + n + 1)
            if x not in first:
                first.append(x)
    return sorted(first, key=lambda x: (-score[x], first.index(x)))


def home_order(blocks: dict, refs: list, now_min: int) -> list:
    """Home's list with nothing typed: two questions, each its own ranked list holding only what it has something to
    say about, fused by rank (`fuse`, no weights; one in both rises, the rest take turns): what's alive for you
    (fw_block.garden's recent, and fading from memory, from your visits) and where to start (the hubs, fw_block.hits:
    pointing at the most-pointed-at, above the average). Then the rest, by last activity (garden's tail)."""
    tended = garden(blocks, refs, now_min)
    alive = [i for i, why in tended if why]
    hub, _ = hits(refs, pericope_edges(blocks, refs))
    starts = sorted((r for r in refs if hub[r] > 1), key=lambda r: -hub[r])
    first = fuse(alive, starts)
    return first + [i for i, _ in tended if i not in set(first)]


EXITS = 6  # where to go from a pericope: this many, at most


def exits(blocks: dict, refs: list, here: str, now_min: int, meaning: list | None = None) -> tuple[list, list]:
    """Where to go from `here` (not what it already points at: that's on the page): four questions, each its own
    ranked list, fused by rank (`fuse`, no weights), the first EXITS. What points here (its backlinks' pericopes, the
    best hubs first); what sits alongside it in the structure (fw_block.alongside, ties, then authority); where you
    go next from it (fw_block.visited_next, from visits); and, with `meaning` (the mini's nearest blocks to its
    text), what's about the same thing. Short of EXITS (nothing points here, no visits, the mini away), filled from
    home's own order (home_order): where you'd start anyway, so a page is never without somewhere to go.
    (related, filled): the page says which is which.""" 
    edges = pericope_edges(blocks, refs)
    hub, auth = hits(refs, edges)
    shown = {b for a, b in edges if a == here} | {here}
    pointing = sorted({a for a, b in edges if b == here}, key=lambda r: -hub[r])
    beside = [r for r, _ in sorted(alongside(edges, here), key=lambda x: (-x[1], -auth[x[0]]))]
    nxt = [r for r, _ in visited_next(blocks, refs, here)]
    tops, near = set(refs), []
    for i in meaning or []:
        r = i if i in tops else (home_of(blocks, i)[0] if i in blocks else None)
        if r in tops and r not in near:
            near.append(r)
    out = fuse(*[[r for r in lst if r not in shown] for lst in (pointing, beside, nxt, near)])[:EXITS]
    return out, [r for r in home_order(blocks, refs, now_min) if r not in shown and r not in out][:EXITS - len(out)]


class Search:
    """A search list over entries, the same wherever one is picked (home, the
    quote search, Link to an entry; the terminal's Picker and the web
    editor's search, fw_web): its rows are worked out from what it's given
    and what's typed (`query`, `shown`, `meaning`), nothing else. Newest
    first, and typing filters by title (or the start of an id). `pinned`
    rows, (key, label(query)), sit above the results. `inside` ({entry:
    [(block, depth), …]}, the blocks in each, in order) makes it a search
    over blocks: it offers those whose title has what's typed, indented
    under their entry (and the entry with them, if it didn't match itself);
    an entry in `shown` lists all its blocks under it. And with what's
    typed, each match brings its kin, dim: the rest of its paraphrase family
    right under it (≈, the same thing said another way), and, below every
    match, the places that quote it (a row per quote, whose key is the quote
    block; `source` turns it into what it quotes). In a search over blocks,
    typing a kind's name puts that kind first, the blocks of that kind under
    it, then the blocks a model guesses are (`guesses`, fw_block.guessed's),
    dim (kind_first); `kinds` are the kinds' ids (a kind's row is drawn
    blue). With `meaning`
    (query, block ids nearest it: the mini's answer, fw_meaning) for what's
    typed, a search over blocks mixes those in by rank (`fuse`): the
    pericopes reordered, blocks found only by meaning listed under theirs,
    "(by meaning)"."""

    def __init__(self, library: dict, refs: list, pinned=(), inside=None, label=None, guesses=None, applied=()):
        self.library, self.refs, self.pinned = library, refs, list(pinned)
        self.guesses = guesses or {}  # {block id: {kind id: p}}: a model's guesses that count
        self.applied = set(applied)    # the learned kinds (fw_block.learned): with blocks inside pericopes, guesses applied (is_applied), listed as said, not dim
        self.label = label  # key -> (left, right) for its row, instead of its title and date (filtered by left)
        self.inside = inside or {}
        self.related = inside is not None  # a search over blocks: kin rows too
        self.query = ""
        self.shown = set()  # the entries whose blocks are listed under them (→), whatever is typed
        self.where = {k: e for e, ks in self.inside.items() for k, _ in ks}  # block -> its entry
        self.kinds = set(kind_ids(library))
        self.meaning = None  # (query, block ids nearest it), the mini's answer (fw_meaning): mixed in while that's what's typed
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
        by_meaning = set()
        if self.related and q and self.meaning and self.meaning[0] == self.query:  # the mini's answer, mixed in
            depth = {k: d for e in self.refs for k, d in self.inside.get(e, [])}
            ranked = []
            for i in self.meaning[1]:
                e = i if i in tops else self.where.get(i)
                if e is None or e in listed or i in listed:
                    continue
                ranked += [e] if e not in ranked else []
                if i != e and all(i != k for k, _ in hits.get(e, [])) and \
                        sum(k in by_meaning for k, _ in hits.get(e, [])) < MEANING_PER:
                    hits[e] = hits.get(e, []) + [(i, depth.get(i, 1))]
                    by_meaning.add(i)
                elif i == e and e not in order:
                    by_meaning.add(e)
            order = fuse(order, ranked)
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
        mark = lambda r: "  (by meaning)" if r in by_meaning else ""
        for r in order:
            out += [row(r, title(r) + mark(r))] + kin(r, "  ")
            for k, d in hits.get(r, []):
                out += [row(k, "  " * d + "· " + title(k) + mark(k))] + kin(k, "  " * (d + 1))
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
