"""Hyperlinks moved along with edits, and backlinks: everything pointing at a block."""

from __future__ import annotations

from fw.block.case import expr_refs, links, paraphrases, quoted
from fw.block.kinds import kinds_of
from fw.block.view import home_of
from fw.draft import BLOCK_RE, is_atom
from fw.lens import changed


def move_span(old: str, new: str, span: list) -> list:
    """Span [start, end] of `old` moved along with the edit that made it `new`: typing inside grows it, at either edge
    stays outside; deleting shrinks it, to an empty span that what's typed there fills again."""
    s, e = span
    if old == new:
        return [s, e]
    p, end_old, end_new = changed(old, new)
    d = len(new) - len(old)
    if s == e and p <= s <= end_old:
        return [p, end_new]
    s2 = s if s < p else s + d if s >= end_old else end_new
    e2 = e if e <= p else e + d if e > end_old else p
    return [s2, e2] if s2 <= e2 else [p, p]


def move_links(old: str, new: str, ls: list) -> list:
    """Every hyperlink of a block of text moved along with an edit of it."""
    return [{**link, "at": move_span(old, new, link["at"])} for link in ls]


def draft_leaves(draft: str) -> list:
    """Where each block of text's text is in a draft: [(id, start, end)]."""
    out, pos, cur = [], 0, None
    for line in draft.split("\n"):
        m = BLOCK_RE.fullmatch(line)
        if m:
            cur = None
            if m.group(1):
                out.append([m.group(1), pos + len(line) + 1, pos + len(line) + 1])
                cur = out[-1]
        elif is_atom(line):
            cur = None
        elif cur is not None:
            cur[2] = pos + len(line)
        pos += len(line) + 1
    return [tuple(leaf) for leaf in out]


def carry_links(old: str, new: str, held: dict) -> dict:
    """Hyperlinks (`held`: each block's in `old`, by id) moved with an edit of a whole draft: each block's in `new`
    ([] for none); text moving to another block (a split, a join) takes its links."""
    leaves = {bid: start for bid, start, _ in draft_leaves(old)}
    spans = [(link, move_span(old, new, [leaves[bid] + link["at"][0], leaves[bid] + link["at"][1]]))
             for bid, ls in held.items() if bid in leaves for link in ls]
    out = {bid: [] for bid, _, _ in draft_leaves(new)}
    for link, (s, e) in spans:
        for bid, start, end in draft_leaves(new):
            if (start <= s < end and e > s and e > start) or (s == e and start <= s <= end):
                out[bid].append({**link, "at": [max(s, start) - start, min(e, end) - start]})
                if s == e:
                    break  # an emptied one stays in one place
    return out


def cut_links(ls: list, a: int, b: int) -> list:
    """The hyperlinks of text[a:b], as offsets into that piece."""
    return [{**link, "at": [max(link["at"][0], a) - a, min(link["at"][1], b) - a]}
            for link in ls if link["at"][0] < b and link["at"][1] > a]


BACKLINK_NAMES = {"quote": ("quote", "quotes"), "masked quote": ("masked quote", "masked quotes"),
                  "link": ("link", "links"), "paraphrase": ("paraphrase", "paraphrases"),
                  "kind": ("pericope with this tag", "pericopes with this tag"),
                  "expression": ("expression", "expressions")}  # (one, more than one)


def backlinks(blocks: dict, ref: str) -> list:
    """What points at `ref` itself from a block some entry reaches, oldest first: quotes (a masked quote of a block
    holding `ref` points at that block), links, paraphrases, a yes for a kind, expressions' @references. Each
    {kind (BACKLINK_NAMES), by, home, at (as home_of), created (the block's; a link's own)}."""
    out = []
    for i, b in blocks.items():
        q = quoted(b)
        points = [("masked quote" if q[1] is not None else "quote", b.get("created"), 0)] if q and q[0] == ref else []
        points += [("link", link.get("created"), link["at"][0]) for link in links(b) if link["to"] == ref]
        points += [(k, b.get("created"), 0) for k, yes in (("paraphrase", paraphrases(b) == ref),
                                                          ("kind", kinds_of(b).get(ref) is True),
                                                          ("expression", ref in expr_refs(b))) if yes]
        if not points:
            continue
        home, start = home_of(blocks, i)
        if home is not None:   # (else loose: held only by the clipboard, or about to be erased)
            out += [{"kind": k, "by": i, "home": home, "at": start + off, "created": c} for k, c, off in points]
    return sorted(out, key=lambda x: (x["created"] or "", x["by"]))


def backlink_summary(found: list) -> str:
    """e.g. "3 · 1 quote, 1 masked quote, 1 link", or "none"."""
    if not found:
        return "none"
    counts = [(sum(x["kind"] == k for x in found), names) for k, names in BACKLINK_NAMES.items()]
    return f"{len(found)} · " + ", ".join(f"{n} {names[n > 1]}" for n, names in counts if n)
