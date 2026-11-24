"""fw_block — the block type: taking blocks apart, their text, titles and
counts. Pure functions over the store's blocks (by id); no files.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from fw_draft import BLOCK_RE, IMAGE_RE, QUOTE_RE, block_line, draft_digest, expr_line, image_line, is_atom, parse_draft, quote_line
from fw_lens import ELLIPSIS, intersect, normalize, shown_only, spans_of, view

def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def human_date(dt: datetime) -> str:
    """e.g. `August 3rd, 2026` — full month name, ordinal day, year."""
    return f"{dt.strftime('%B')} {_ordinal(dt.day)}, {dt.year}"


TITLE_MAX_CHARS = 60


_SEP_RE = re.compile(r"^-{2,}")


_LEAD_MARKUP_RE = re.compile(r"^[#>\-\*\s]+")


def derive_title(content: str) -> str | None:
    """A short title guessed from the entry text: the first real line, minus
    append separators and leading markdown/quote noise, clipped to a word
    boundary. None when there's nothing usable to name it by."""
    for raw in content.splitlines():
        line = _LEAD_MARKUP_RE.sub("", raw.strip()).strip().strip("\"'“”")
        if not line or _SEP_RE.match(raw.strip()):
            continue
        if len(line) <= TITLE_MAX_CHARS:
            return line.rstrip(".,;:—- ")
        clipped = line[:TITLE_MAX_CHARS].rsplit(" ", 1)[0].rstrip(".,;:—- ")
        return (clipped or line[:TITLE_MAX_CHARS].rstrip()) + "…"
    return None


def word_count(content: str) -> int:
    return len(content.split())


def index(data: dict) -> dict:
    """Every block by id."""
    return {b.get("id"): b for b in data["blocks"]}


# --- the block type ----------------------------------------------------------
# A block is { id, title, created, words, content }, and content is one of:
#
#   Text    "a string"
#   Blocks  ["<id>", "<id>", …]                 its children, in order
#   Quote   {"quote": "<id>", "mask": [ … ], "show": [ … ], "inner": {"<quote id>": [ … ]}, "lock": true}
#                                               a live view of another block; `show`: which of
#                                               its properties its box's top line shows; `inner`:
#                                               masks of the quotes inside what it shows, seen
#                                               through it (each only hides more); `lock`: no
#                                               writing through it (locked_by)
#   Image   {"image": "<file>"}                 one picture
#   Kind    {"kind": "<name>", "blocks": ["<id>", …]}
#                                               what a block can be (a poem, a to-do): a short
#                                               name, and a description made of child blocks,
#                                               held as a Blocks block holds its children
#
# The functions below take a block apart by which of these it is (match).
# A mask, as the code works with it, is anchors into the target's draft
# (fw_lens); on disk it's per block (masks_out, masks_in).

def children(b: dict | None) -> list:
    """A Blocks block's children (ids), or a Kind's (its description), else none."""
    match b.get("content") if b else None:
        case list(kids) | {"kind": str(), "blocks": list(kids)}:
            return kids
    return []


def kind_of(b: dict | None) -> str | None:
    """A Kind block's name, else None."""
    match b.get("content") if b else None:
        case {"kind": str(name), "blocks": list()}:
            return name
    return None


def block_type(b: dict | None) -> str:
    """What block `b` is, by its content's case (the header's type, derived,
    never stored): "text", "paraphrase", "image", "kind", "quote", or "block"
    (it holds blocks)."""
    match b.get("content") if b else None:
        case str():
            return "text"
        case {"paraphrase": str(), "text": str()}:
            return "paraphrase"
        case {"image": str()}:
            return "image"
        case {"kind": str(), "blocks": list()}:
            return "kind"
        case {"quote": str()}:
            return "quote"
        case {"expr": str()}:
            return "expression"
    return "block"


def type_label(b: dict | None, blocks: dict | None = None) -> str:
    """Block `b`'s type as its header's top line shows it: a kind's says
    which, "kind: poem". With `blocks` (the web's header), a pericope says
    what it is as a whole (the user, 2026-11-23: "if we have a pericope which
    has one block, the type of the pericope should be the type of that one
    block", never "block"): its one block's type (text, quote, image), else
    "pericope" (several, none, or one that holds blocks)."""
    if kind_of(b) is not None:
        return f"tag: {kind_of(b)}"   # (called a tag, the user, 2026-11-24; kinds in the code)
    if blocks is None or not (b or {}).get("entry") or block_type(b) != "block":
        return block_type(b)
    kids = [k for k in children(b) if k in blocks]
    one = block_type(blocks[kids[0]]) if len(kids) == 1 else "block"
    return one if one != "block" else "pericope"


def without(b: dict, key: str) -> dict:
    """Block `b` without field `key` (a new block; `b` as it was)."""
    return {k: v for k, v in b.items() if k != key}


def with_children(b: dict, kids: list) -> dict:
    """Block `b` with these children (a new block): a Kind keeps its name, anything else becomes Blocks."""
    name = kind_of(b)
    return {**b, "content": {"kind": name, "blocks": kids} if name is not None else kids}


def quoted(b: dict | None) -> tuple | None:
    """A Quote block's (target id, mask or None), else None: the mask as it
    shows, without its empty places (`raw_mask` has them)."""
    match b.get("content") if b else None:
        case {"quote": str(target), **rest}:
            return target, shown_only(rest.get("mask"))
    return None


def raw_mask(b: dict | None) -> list | None:
    """A Quote block's mask with its empty places (fw_lens): for the writes
    that move it along."""
    match b.get("content") if b else None:
        case {"quote": str(), **rest}:
            return rest.get("mask")
    return None


MAX_DEPTH = 3  # quotes inside quotes inside quotes; deeper ones show as one "⋯" line

SHOWABLE = ("title", "created", "updated", "words")  # what a quote's top line can show, in this order


def is_whole(b: dict | None) -> bool:
    """A block that's one thing whole, with no text to write in (an image;
    any such case added later goes here too): selected whole, never gone
    into, even through a quote of it."""
    return image_of(b) is not None


def expr_of(b: dict | None) -> str | None:
    """An expression block's source (the expr branch: {"expr": source}, a program the page evaluates), else None."""
    match b.get("content") if b else None:
        case {"expr": str(src)}:
            return src
    return None


EXPR_REF = re.compile(r"@([0-9]{8}T[0-9]{6}-[0-9a-f]{4})")


def expr_refs(b: dict | None) -> list:
    """The pericopes and blocks an expression block's source refers to (`@<id>`), in order, each once."""
    out = []
    for m in EXPR_REF.finditer(expr_of(b) or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def image_of(b: dict | None) -> str | None:
    """An Image block's picture: its file's name (in the store's images folder), else None."""
    match b.get("content") if b else None:
        case {"image": str(name)}:
            return name
    return None


def quote_show(b: dict | None) -> list:
    """Which properties a Quote block's top line shows (none, if it isn't a quote)."""
    match b.get("content") if b else None:
        case {"quote": str(), "show": list(show)}:
            return [k for k in SHOWABLE if k in show]
    return []


def quote_lock(b: dict | None) -> bool:
    """Whether Quote block `b` is locked: no writing through it (not, if it isn't a quote)."""
    match b.get("content") if b else None:
        case {"quote": str(), "lock": True}:
            return True
    return False


def locked_by(blocks: dict, path: list) -> str | None:
    """The quote that keeps you from writing at the end of `path`, the quote
    blocks open from the pericope inward, outermost first (a place in the
    pericope: []; inside the last of them: all of them): the outermost one
    that's locked, else None, and you can write there. Everything shown
    through a locked quote is locked too, at any depth; a locked quote
    inside an unlocked one locks itself and what's under it. A quote's own
    properties (its mask, top line, lock) are written in the block that
    holds it: free when the path to it, without it, is."""
    return next((q for q in path if quote_lock(blocks.get(q))), None)


def quote_inner(b: dict | None) -> dict:
    """A Quote block's masks for the quotes inside what it shows (by quote id)."""
    match b.get("content") if b else None:
        case {"quote": str(), "inner": dict(inner)}:
            return inner
    return {}


def merge_inner(a: dict, b: dict) -> dict:
    """Two quotes' inner masks, one seen through the other: both narrow."""
    return {**a, **b, **{k: intersect(a[k], b[k]) for k in a.keys() & b.keys()}}


def seen_quote(blocks: dict, qid: str, inner: dict) -> tuple:
    """Quote block `qid` as it's seen through quotes whose inner masks are
    `inner`: ("quote", target, its mask narrowed by theirs, show, the inner
    masks in force inside it)."""
    b = blocks.get(qid)
    target, mask = quoted(b)
    return ("quote", target, intersect(mask, inner.get(qid)), quote_show(b), merge_inner(inner, quote_inner(b)))


def paraphrases(b: dict | None) -> str | None:
    """What Paraphrase block `b` paraphrases (the original's id), else None."""
    b = b.get("block", b) if b else None
    match b.get("content") if b else None:
        case {"paraphrase": str(src), "text": str()}:
            return src
    return None


def text_of(b: dict | None) -> str | None:
    """A block's own text when it's a block of text: a Text block's string, a
    Paraphrase's words (the user, 2026-11-21: a paraphrase is a block like a
    quote, drawn as text); else None."""
    match b.get("content") if b else None:
        case str(text) | {"paraphrase": str(), "text": str(text)}:
            return text
    return None


def with_text(b: dict, text: str) -> dict:
    """Block `b` with this text (a new block): a paraphrase stays one, of the
    same original; anything else becomes Text."""
    src = paraphrases(b)
    return {**b, "content": {"paraphrase": src, "text": text} if src else text}


def links(b: dict | None) -> list:
    """A block's hyperlinks: [{"to": entry id, "at": [start, end]}] on its text."""
    return list(b.get("links", [])) if b else []


def move_span(old: str, new: str, span: list) -> list:
    """Hyperlink span [start, end] of text `old`, moved along with an edit
    that made it `new` (the changed stretch is where the two differ). Edits
    before or after it move it; typing inside it grows it, but text typed at
    either edge stays outside; text of it deleted shrinks it, to nothing
    (kept: an empty span grows again with what's typed where it is, so an
    undo, or retyping, brings it back)."""
    s, e = span
    if old == new:
        return [s, e]
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    q = 0
    while q < min(len(old), len(new)) - p and old[-1 - q] == new[-1 - q]:
        q += 1
    end_old, end_new, d = len(old) - q, len(new) - q, len(new) - len(old)
    if s == e and p <= s <= end_old:  # empty: what's typed here is it again
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
    """Hyperlinks moved along with an edit of a whole draft, `old` -> `new`:
    `held` has each block's links in `old` (by id); returns each block's in
    `new` (by id, [] for none). As one edit of the whole draft, text moving
    to another block (Enter splitting one, Backspace joining two) takes its
    links with it."""
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


def with_links(b: dict, ls: list) -> dict:
    """Block `b` with these hyperlinks (a new block; none: no `links`)."""
    return {**b, "links": ls} if ls else without(b, "links")


def cut_links(ls: list, a: int, b: int) -> list:
    """The hyperlinks of text[a:b], as offsets into that piece."""
    return [{**link, "at": [max(link["at"][0], a) - a, min(link["at"][1], b) - a]}
            for link in ls if link["at"][0] < b and link["at"][1] > a]


def pretty_time(iso: str | None, clock: bool = True) -> str:
    """An ISO date-time as people write it: "Oct 21, 2026, 3:04 pm" (or just the date)."""
    try:
        t = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    date = f"{t:%b} {t.day}, {t.year}"
    return f"{date}, {t.hour % 12 or 12}:{t:%M} {'am' if t.hour < 12 else 'pm'}" if clock else date


def own_text(blocks: dict, ref: str, seen: frozenset = frozenset()) -> str:
    """A block's own text: its text, or its children's in order. A quote or an image has none."""
    b = blocks.get(ref)
    if b is None or ref in seen:
        return ""
    match b.get("content", ""):
        case str(text) | {"paraphrase": str(), "text": str(text)} | {"expr": str(text)}:   # (an expression's: its source)
            return text
        case list() | {"kind": str(), "blocks": list()}:
            return "\n".join(own_text(blocks, k, seen | {ref}) for k in children(b)
                             if not (quoted(blocks.get(k)) or image_of(blocks.get(k))))
    return ""


def block_items(blocks: dict, ref: str, seen: frozenset = frozenset(), inner: dict | None = None) -> list:
    """What a block shows, in order: ("text", text) for its text and each
    child's, ("quote", target, mask, show, inner) for each quote in it, seen
    through `inner`, ("image", id) for each image (the inner masks of the quotes it's seen through). A
    quote shows its view (text there keeps its ELLIPSIS marks)."""
    inner = inner or {}
    b = blocks.get(ref)
    if b is None or ref in seen:
        return []
    match b.get("content", ""):
        case str(text) | {"paraphrase": str(), "text": str(text)}:
            return [("text", text)]
        case list() | {"kind": str(), "blocks": list()}:
            out = []
            for k in children(b):
                if quoted(blocks.get(k)):
                    out.append(seen_quote(blocks, k, inner))
                elif image_of(blocks.get(k)):
                    out.append(("image", k))
                elif expr_of(blocks.get(k)) is not None:   # (an expression: what it shows is worked out in the page)
                    out.append(("expr", k))
                else:
                    out += block_items(blocks, k, seen | {ref}, inner)
            return out
        case {"quote": str(target), **rest}:
            _, _, mask, _, deeper = seen_quote(blocks, ref, inner)
            return quote_items(blocks, target, mask, seen | {ref}, deeper)
        case {"image": str()}:
            return [("image", ref)]
    return []


def items_text(blocks: dict, items: list, seen: set, own: bool = True) -> str:
    """The text of `items` (as from block_items) with each quote's text
    flattened in, in order. Each block's text counts once: a block already
    in `seen` (quoted twice, or in a loop) is left out. With own=False, only
    the quoted text."""
    parts = []
    for item in items:
        match item:
            case ("text", text):
                if own:
                    parts.append(text.replace(ELLIPSIS, ""))
            case ("quote", target, mask, _, inner) if target in blocks and target not in seen:
                seen.add(target)
                parts.append(items_text(blocks, quote_items(blocks, target, mask, inner=inner), seen))
    return "\n".join(p for p in parts if p)


def full_text(blocks: dict, ref: str, own: bool = True) -> str:
    """Everything a block shows as text: its own, then what it quotes, flattened."""
    return items_text(blocks, block_items(blocks, ref), {ref}, own) if ref in blocks else ""


def shown_text(blocks: dict, ref: str) -> str:
    """What a block shows, as plain text: quotes flattened in, each hidden
    stretch written as …. (What a quote turns into when it's detached.)"""
    parts = []
    for item in block_items(blocks, ref):
        match item:
            case ("text", text):
                parts.append(text.replace(ELLIPSIS, "…"))
            case ("quote", target, mask, _, inner) if target in blocks:
                parts.append(items_text(blocks, quote_items(blocks, target, mask, inner=inner), {ref, target}))
    return "\n".join(p for p in parts if p)


# --- the draft: a block as the plain text the editor edits -------------------

def block_draft(blocks: dict, ref: str) -> str:
    """A block -> the plain text the editor edits: each child's text after a
    marker line naming it, each quote as one line naming its target and
    itself. A child that holds blocks of its own (a container) is drafted
    as its children, each naming it too (and the containers it's in), to any depth."""
    match blocks[ref].get("content", ""):
        case str(text) | {"paraphrase": str(), "text": str(text)}:
            return text
        case list() | {"kind": str(), "blocks": list()}:  # (a kind: its description's blocks)
            return "\n".join(child_lines(blocks, children(blocks[ref])))
    return ""  # a quote is drafted where it's quoted, as its line


def child_lines(blocks: dict, kids: list, within: tuple = ()) -> list:
    """The draft lines of children `kids` (in the containers `within`, innermost first)."""
    out = []
    for k in kids:
        q = quoted(blocks.get(k))
        if q:
            out.append(quote_line(q[0], k, within))
        elif image_of(blocks.get(k)):
            out.append(image_line(k, within))
        elif expr_of(blocks.get(k)) is not None:
            out.append(expr_line(k, expr_of(blocks[k]), within))
        elif children(blocks.get(k)) and k not in within:
            out += child_lines(blocks, children(blocks[k]), (k, *within))
        elif k in blocks:
            out += [block_line(k, within), own_text(blocks, k)]
    return out


def ancestors(blocks: dict, ref: str) -> list:
    """Every block `ref` is inside (its parents, theirs, …), up to the entries."""
    out, todo = [], parents(blocks, ref)
    while todo:
        i = todo.pop()
        if i not in out and i != ref:
            out.append(i)
            todo += parents(blocks, i)
    return out


def content_hash(blocks: dict, ref: str) -> str | None:
    """A fingerprint of what a block shows (its text, how it's split into
    blocks, its quotes and their masks; not the ids): an editor keeps it as
    the `base` its text was built on, so a commit can tell when the block
    changed elsewhere in the meantime."""
    return draft_digest(json.dumps(block_items(blocks, ref))) if ref in blocks else None


def with_mask(b: dict, mask: list | None) -> dict:
    """Quote block `b` with a new mask (a new block; None: show all of it); the rest of it stays."""
    rest = {k: v for k, v in b["content"].items() if k != "mask"}
    return {**b, "content": {**rest, "mask": mask} if mask is not None else rest}


def home_of(blocks: dict, ref: str) -> tuple:
    """Where block `ref` lives: (the entry it's in, where it starts in that
    entry's draft). An entry is its own home; one in no entry, None."""
    if blocks.get(ref, {}).get("entry"):
        return ref, 0
    home = next((i for i in ancestors(blocks, ref) if blocks[i].get("entry")), None)
    if home is None:
        return None, 0
    draft, inside = block_draft(blocks, home), set(subtree(blocks, ref))
    return home, next((s for i, s, _, _ in regions(blocks, home, draft) if i in inside), 0)


# --- masks on disk: per block -------------------------------------------------
# On disk a mask says what shows of each block of its target, like a block's
# links: {block id: [[start, end], …]}, spans of that block's own text, a
# quote inside it one place ([[0, 1]]: it shows). A block it doesn't list
# shows nothing. In memory it's anchors into the target's draft, for the
# lens; these turn one into the other as the store is read and written.

def regions(blocks: dict, ref: str, draft: str) -> list:
    """Where each block of `ref`'s draft is in it, in order: (id, start, end,
    whether it's a quote or an image, one place): a block of text's own text, a quote's or image's line."""
    if text_of(blocks[ref]) is not None:
        return [(ref, 0, len(draft), False)]
    out, pos, cur = [], 0, None
    for line in draft.split("\n"):
        end = pos + len(line)
        if m := BLOCK_RE.fullmatch(line):
            cur = [m.group(1), end + 1, end + 1, False]
            out.append(cur)
        elif m := QUOTE_RE.fullmatch(line) or IMAGE_RE.fullmatch(line):
            out.append([m.group(2) if m.re is QUOTE_RE else m.group(1), pos, end, True])
            cur = None
        elif cur is not None:
            cur[2] = end
        pos = end + 1
    return [tuple(r) for r in out]


def mask_to(blocks: dict, ref: str, draft: str, block: str) -> list:
    """Anchors into `draft` (`ref`'s) showing just `block` and all it holds."""
    inside = set(subtree(blocks, block))
    return [x for i, s, e, _ in regions(blocks, ref, draft) if i in inside and e > s for x in (s, e)]


def backlinks(blocks: dict, ref: str) -> list:
    """The blocks pointing at `ref` itself, oldest first: each quote of it
    (masked or not: a masked quote of a block holding `ref` points at that
    block, not at `ref`) and each hyperlink to it, in a block some entry
    reaches, each paraphrase of it, and, for a kind, each
    block you said is one. Each a dict: kind ("quote", "masked quote",
    "link", "paraphrase", "kind": BACKLINK_NAMES says them), `by` (the
    pointing block), `home` and `at` (the entry it's in, and where in that
    entry's draft, as home_of), `created` (a quote's block's; a link's own,
    None before links were dated)."""
    out = []
    for i, b in blocks.items():
        q = quoted(b)
        points = [("masked quote" if q[1] is not None else "quote", b.get("created"), 0)] if q and q[0] == ref else []
        points += [("link", link.get("created"), link["at"][0]) for link in links(b) if link["to"] == ref]
        points += [("paraphrase", b.get("created"), 0)] if paraphrases(b) == ref else []
        points += [("kind", b.get("created"), 0)] if kinds_of(b).get(ref) is True else []
        points += [("expression", b.get("created"), 0)] if ref in expr_refs(b) else []   # (TYPE.md: any @ref counts)
        if not points:
            continue
        home, start = home_of(blocks, i)
        if home is None:
            continue  # (loose: held only by the clipboard, or about to be erased)
        out += [{"kind": k, "by": i, "home": home, "at": start + off, "created": c} for k, c, off in points]
    return sorted(out, key=lambda x: (x["created"] or "", x["by"]))


BACKLINK_NAMES = {"quote": ("quote", "quotes"), "masked quote": ("masked quote", "masked quotes"),
                  "link": ("link", "links"), "paraphrase": ("paraphrase", "paraphrases"),
                  "kind": ("pericope with this tag", "pericopes with this tag"),
                  "expression": ("expression", "expressions")}  # (one, more than one)


def backlink_summary(found: list) -> str:
    """e.g. "3 · 1 quote, 1 masked quote, 1 link", or "none"."""
    if not found:
        return "none"
    counts = [(sum(x["kind"] == k for x in found), names) for k, names in BACKLINK_NAMES.items()]
    return f"{len(found)} · " + ", ".join(f"{n} {names[n > 1]}" for n, names in counts if n)


def families(blocks: dict) -> dict:
    """The paraphrase families: the blocks joined by paraphrasing (a
    source, what paraphrases it, what paraphrases those, …), the same thing
    said more than one way. {member: [every member, oldest first]}, for the
    blocks in a family of two or more. Works on the store's blocks or the
    editor's library alike."""
    near = {}
    for i, b in blocks.items():
        s = paraphrases(b)
        if s in blocks and s != i:
            near.setdefault(i, set()).add(s)
            near.setdefault(s, set()).add(i)
    out = {}
    for start in near:
        if start in out:
            continue
        group, todo = set(), [start]
        while todo:
            i = todo.pop()
            if i not in group:
                group.add(i)
                todo += near[i]
        members = sorted(group)  # (ids sort by creation)
        out.update((i, members) for i in members)
    return out


def per_block(regs: list, mask: list | None) -> dict | None:
    """Anchors -> what shows of each block (on disk)."""
    if mask is None:
        return None
    spans, out = spans_of(mask), {}
    for bid, s, e, quote in regs:
        if quote:
            got = [[0, 1]] if any(a < e and b > s for a, b in spans) else []
        else:
            got = [[max(a, s) - s, min(b, e) - s] for a, b in spans
                   if a < b and (max(a, s) < min(b, e) or s == e and a <= s and e <= b)
                   or a == b and s <= a <= e]  # (an empty place: fw_lens)
        if got:
            out[bid] = got
    return out


def flat_mask(regs: list, draft: str, mask: dict | None) -> list | None:
    """What shows of each block (on disk) -> anchors into the draft. A quote
    shown is a span from the text before it to the text after (as an anchor
    can't sit in its line)."""
    if mask is None:
        return None
    spans = []
    for n, (bid, s, e, quote) in enumerate(regs):
        if bid not in mask:
            continue
        if quote:
            spans.append([regs[n - 1][2] if n else 0, regs[n + 1][1] if n + 1 < len(regs) else len(draft)])
        else:
            spans += [[s + a, s + min(b, e - s)] for a, b in mask[bid] if 0 <= a <= b]
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return normalize(draft, [x for span in merged for x in span], keep_empty=True)


def convert_masks(blocks_list: list, to_disk: bool) -> list:
    """Every Quote block's mask and inner masks turned per block (to disk) or
    into anchors (from it); a block that isn't a masked quote is passed as is."""
    blocks, drafts = {b.get("id"): b for b in blocks_list}, {}
    def turn(target: str, mask):
        if target not in blocks or mask is None:
            return mask
        if target not in drafts:
            draft = block_draft(blocks, target)
            drafts[target] = (draft, regions(blocks, target, draft))
        draft, regs = drafts[target]
        return per_block(regs, mask) if to_disk else flat_mask(regs, draft, mask)
    out = []
    for b in blocks_list:
        c = b.get("content")
        if not (isinstance(c, dict) and ("mask" in c or "inner" in c)):
            out.append(b)
            continue
        c = dict(c)
        if "mask" in c:
            c["mask"] = turn(c["quote"], c["mask"])
        if "inner" in c:
            c["inner"] = {k: turn(quoted(blocks[k])[0], m) for k, m in c["inner"].items()
                          if quoted(blocks.get(k))}  # (one for a quote that's gone goes with it)
        out.append({**b, "content": c})
    return out


def masks_out(blocks_list: list) -> list:
    """The blocks as they're written to disk: masks per block."""
    return convert_masks(blocks_list, True)


def masks_in(blocks_list: list) -> list:
    """The blocks as read from disk, masks as anchors for the lens."""
    return convert_masks(blocks_list, False)


def with_inner(b: dict, inner: dict) -> dict:
    """Quote block `b` with new masks for the quotes inside it (a new block; none: no `inner`)."""
    rest = {k: v for k, v in b["content"].items() if k != "inner"}
    return {**b, "content": {**rest, "inner": inner} if inner else rest}


def with_show(b: dict, show: list) -> dict:
    """Quote block `b` with what its top line shows (a new block; none: no `show`)."""
    rest = {k: v for k, v in b["content"].items() if k != "show"}
    return {**b, "content": {**rest, "show": [k for k in SHOWABLE if k in show]} if show else rest}


def with_lock(b: dict, on: bool) -> dict:
    """Quote block `b` locked (a new block; or unlocked: no `lock`)."""
    rest = {k: v for k, v in b["content"].items() if k != "lock"}
    return {**b, "content": {**rest, "lock": True} if on else rest}


def quote_items(blocks: dict, ref: str, mask: list | None, seen: frozenset = frozenset(),
                inner: dict | None = None) -> list:
    """What a quote of `ref` shows: its items, or with a mask, the items of
    its view (text keeps its ELLIPSIS marks); the quotes in it seen through
    `inner`."""
    inner = inner or {}
    if mask is None or ref not in blocks:
        return block_items(blocks, ref, seen, inner)
    lines, bids = parse_draft(view(block_draft(blocks, ref), mask))
    items, last = [], None
    for line, bid in zip(lines, bids):
        m = QUOTE_RE.fullmatch(line)
        if image := IMAGE_RE.fullmatch(line):
            items.append(("image", image.group(1)))
        elif m:
            if m.group(2) and quoted(blocks.get(m.group(2))):
                items.append(seen_quote(blocks, m.group(2), inner))
            else:
                items.append(("quote", m.group(1), None, [], inner))
        elif items and items[-1][0] == "text" and bid == last:
            items[-1] = ("text", items[-1][1] + "\n" + line)
        else:
            items.append(("text", line))
        last = bid
    return items


def parents(blocks: dict, ref: str) -> list:
    return [i for i, b in blocks.items() if ref in children(b)]


def held(blocks: dict) -> set:
    """Every block some block holds as a child."""
    return {k for b in blocks.values() for k in children(b)}


def loose(blocks: dict, ref: str, holders: set | None = None) -> bool:
    """A block nothing holds that isn't an entry: one put back by an undo, or
    pasted, before the block it goes in is saved (which then takes it as its
    own). `holders`: held(blocks), when asking about many at once."""
    b = blocks.get(ref)
    return b is not None and not b.get("entry") and ref not in (held(blocks) if holders is None else holders)


def is_empty_untitled(blocks: dict, ref: str) -> bool:
    """No text, no written title and no quotes or images: nothing worth
    keeping (a kind always is: it has its name)."""
    b = blocks[ref]
    return (kind_of(b) is None and not own_text(blocks, ref).strip() and not b.get("title")
            and not any(item[0] in ("quote", "image") for item in block_items(blocks, ref)))  # (one nested in a child too)


def display_title(blocks: dict, ref: str, named: dict | None = None) -> str | None:
    """A kind's name (it's its title), else the written title, else one
    derived from the first line, else from what else it holds: a picture,
    the title a model gave it (`named`, {file name: title}, written beside the store by a model:
    picture-titles.json), else "picture"."""
    return (kind_of(blocks[ref]) or blocks[ref].get("title") or derive_title(own_text(blocks, ref))
            or (named or {}).get(image_of(blocks[ref]))
            or ("picture" if any(item[0] == "image" for item in block_items(blocks, ref)) else None))


# --- pictures are pericopes ------------------------------------------------------
# A picture is never held inside another block (the user, 2026-11-17): it's a
# pericope of its own, quoted where it's shown. Held anywhere, it's taken out:
# it becomes an entry and a quote of it takes its place (fw_store's
# pictures_apart, on every write). The quote's id comes from the picture's and
# its holder's, so two machines doing it make the same block.

def pictures_held(blocks: dict) -> list:
    """(holder, picture) for every picture block a block holds as a child."""
    return [(i, k) for i, b in blocks.items() for k in children(b.get("block", b))
            if image_of((blocks.get(k) or {}).get("block", blocks.get(k)))]


def picture_quote_id(picture: str, holder: str, taken=frozenset()) -> str:
    """The id of the quote that takes picture `picture`'s place in `holder`:
    the picture's time, and four hex digits from the two ids (another, if
    those are `taken`)."""
    n = 0
    while True:
        h = hashlib.sha1(f"picture {picture} in {holder} {n}".encode()).hexdigest()[:4]
        qid = picture[:16] + h
        if qid not in taken:
            return qid
        n += 1


def entry_ids(data: dict) -> list[str]:
    """The entries: the top-level blocks, the ones marked `entry`."""
    return [b["id"] for b in data["blocks"] if b.get("entry")]


def build_library(data: dict, named: dict | None = None) -> dict:
    """Every block by id, as the editor needs it to draw quotes and fill the
    / menu (`named`: pictures' titles from a model, display_title)."""
    blocks = index(data)
    return {i: {"title": display_title(blocks, i, named) or "untitled", "words": b.get("words", 0),
                "content": b.get("content", ""), "entry": bool(b.get("entry")), "block": b} for i, b in blocks.items()}


def sorted_entries(data: dict) -> list[dict]:
    return sorted((b for b in data["blocks"] if b.get("entry")), key=lambda b: b.get("created", ""))


def subtree(blocks: dict, ref: str) -> list:
    """`ref` and every block under it (children, theirs, …; not what it quotes).
    Works on the store's blocks or the editor's library alike."""
    def block(i):
        b = blocks.get(i)
        return b.get("block", b) if b else None
    out, todo = [], [ref]
    while todo:
        i = todo.pop()
        if i not in out and block(i) is not None:
            out.append(i)
            todo += children(block(i))
    return out


# --- visits: stretches of attention on a block (schema v15) -------------------
#
# On disk a block's `visits` is {"total": n, "first": minute, "recent":
# [[minute, flags], …]}: the last VISITS_KEPT visits, oldest first, each the
# minute it began (minutes since the epoch) and what happened in it (FLAGS:
# o opened, c the cursor stayed in it, w written in, q through a quote).
# Never an edit: not part of `updated`, words, content_hash or undo.

VISIT_GAP = 600      # seconds without attention on a block that end its visit
VISIT_DWELL = 3      # seconds the cursor stays in a block before passing through it counts
VISITS_KEPT = 10     # visits kept per block (the total and the first go on counting)
FLAGS = "ocwq"


def visits(b: dict | None) -> list:
    """A block's recent visits, [[minute, flags], …], oldest first (for ranking later)."""
    return [list(r) for r in ((b or {}).get("visits") or {}).get("recent", [])]


def last_visit(b: dict | None) -> int | None:
    """The minute the block's latest visit began, or None if it has none."""
    rs = visits(b)
    return rs[-1][0] if rs else None


def minute_iso(minute: int | None) -> str:
    """A visit's minute as a local ISO date-time ("" for none), for showing like `updated`."""
    return "" if minute is None else datetime.fromtimestamp(minute * 60).astimezone().isoformat(timespec="seconds")


def flags_union(a: str, b: str) -> str:
    return "".join(f for f in FLAGS if f in a or f in b)


def add_visits(v: dict | None, records: dict) -> dict:
    """Visits `v` with `records` ({minute: flags}) merged in: one beginning
    in a minute already there joins it (its flags added, not counted again);
    a new one is counted. Keeps the last VISITS_KEPT."""
    recent = {m: f for m, f in (v or {}).get("recent", [])}
    total, first = (v or {}).get("total", 0), (v or {}).get("first")
    for m, f in records.items():
        m = int(m)
        if m not in recent:
            total += 1
        recent[m] = flags_union(recent.get(m, ""), f)
        first = m if first is None else min(first, m)
    rs = sorted(recent.items())[-VISITS_KEPT:]
    return {"total": max(total, len(rs)), "first": first, "recent": [[m, f] for m, f in rs]}


def merge_visits(a: dict | None, b: dict | None, base: dict | None = None) -> dict | None:
    """Two copies of a block's visits made one (when syncing two stores): the union of their
    recent visits; the total counts what each side added since `base` (the
    copy both came from), else the larger. None if neither has any."""
    if not a and not b:
        return None
    out = add_visits(a, {m: f for m, f in (b or {}).get("recent", [])})
    ta, tb, t0 = (x.get("total", 0) if x else 0 for x in (a, b, base))
    out["total"] = max(ta + tb - t0 if base else max(ta, tb), len(out["recent"]))
    firsts = [x["first"] for x in (a, b) if x and x.get("first") is not None]
    out["first"] = min(firsts) if firsts else out["first"]
    return out


def with_visits(b: dict, v: dict | None) -> dict:
    """Block `b` with visits `v` (a new block; None: none)."""
    return {**b, "visits": v} if v else without(b, "visits")


def attend(live: dict, ids, flags: str, at: float) -> tuple[dict, dict]:
    """Attention on blocks `ids` at `at` (seconds since the epoch). `live`
    is the visits under way, {id: (minute it began, last attention)}: each
    carries on, or a new one begins once VISIT_GAP has passed. Returns (the
    new `live`, {id: (minute it began, flags)} to record)."""
    live, out = dict(live), {}
    for i in ids:
        start, last = live.get(i, (None, None))
        if start is None or at - last > VISIT_GAP:
            start = int(at // 60)
        live[i] = (start, max(at, last or at))
        out[i] = (start, flags)
    return live, out


def note_visits(pending: dict, records: dict) -> dict:
    """Visits waiting to be written, {id: {minute: flags}}, with `records`
    (from attend) added."""
    out = {i: dict(r) for i, r in pending.items()}
    for i, (m, f) in records.items():
        out.setdefault(i, {})[m] = flags_union(out.get(i, {}).get(m, ""), f)
    return out


def ended(live: dict, at: float) -> set:
    """The visits under way that have ended by `at`: VISIT_GAP without attention."""
    return {i for i, (_, last) in live.items() if at - last > VISIT_GAP}


# --- the garden: what home shows first ------------------------------------------
#
# A small FSRS-style memory per block, read from its visits (never stored):
# each visit is a review, graded by what happened in it (written in counts
# most, a glance least). Stability S (days) grows most when a visit comes
# after the block had started to fade; retrievability R = (1 + t/(9S))^-1 is
# how well it's still in mind t days after the last visit. The garden puts
# the recently active first, then what has dropped out of memory (R under
# FADED_AT), the most rehearsed first, then the rest by last activity.

RECENT_DAYS = 7      # active this recently: "recent"
FADED_AT = 0.9       # R under this: dropped out of memory (FSRS's usual target retention)
RESURFACE = 12       # at most this many resurfacing cards
TOP = 10             # the first cards: recent and resurfacing taken in turn
GRADE = {"w": 1.0, "c": 0.7, "q": 0.6, "o": 0.4}  # a visit's weight, by its strongest flag
S_FIRST = 1.0        # stability (days) after the first visit or the writing


def iso_minute(stamp: str | None) -> int | None:
    """An ISO `created`/`updated` stamp as minutes since the epoch (None if unreadable)."""
    try:
        return int(datetime.fromisoformat(stamp).timestamp() // 60)
    except (TypeError, ValueError):
        return None


def grade(flags: str) -> float:
    return max((GRADE[f] for f in flags if f in GRADE), default=GRADE["o"])


def retrievability(stability: float, days: float) -> float:
    return (1 + max(days, 0) / (9 * stability)) ** -1


def memory(b: dict | None, now_min: int) -> tuple[float, float]:
    """(stability in days, retrievability now) of block `b`, replayed from its
    visits (its `created` stands for the first if it has none)."""
    rs = visits(b)
    first = ((b or {}).get("visits") or {}).get("first")
    reviews = [(m, f) for m, f in rs]
    if first is not None and (not reviews or first < reviews[0][0]):
        reviews.insert(0, (first, "o"))
    if not reviews:
        made = iso_minute((b or {}).get("created"))
        reviews = [(made, "w")] if made is not None else []
    if not reviews:
        return S_FIRST, 0.0
    s, last = S_FIRST, reviews[0][0]
    for m, f in reviews[1:]:
        r = retrievability(s, (m - last) / 1440)
        s *= 1 + 26.9 * s ** -0.15 * (2.718281828 ** (1 - r) - 1) * grade(f)  # e^1.5·(11−5) ≈ 26.9
        last = m
    return s, retrievability(s, (now_min - last) / 1440)


def last_active(b: dict | None) -> int | None:
    """The latest minute block `b` was visited or changed."""
    times = [t for t in (last_visit(b), iso_minute((b or {}).get("updated"))) if t is not None]
    return max(times) if times else None


def last_action(b: dict | None) -> tuple[str, int | None]:
    """What last happened to `b` and when: ("written" | "read" | "opened" |
    "seen in a quote" | "edited" | "made", minute)."""
    rs, upd = visits(b), iso_minute((b or {}).get("updated"))
    if rs and (upd is None or rs[-1][0] >= upd - 10):
        f = rs[-1][1]
        return ("written" if "w" in f else "read" if "c" in f else "seen in a quote" if "q" in f
                else "opened"), rs[-1][0]
    if upd is not None and upd > (iso_minute((b or {}).get("created")) or upd) + 1:
        return "edited", upd
    return "made", iso_minute((b or {}).get("created"))


def garden(blocks: dict, refs: list, now_min: int) -> list[tuple[str, str]]:
    """`refs` (entries) in the garden's order, each with why it's there:
    "recent", "resurfacing" or "" (the rest). The first TOP mix the two, in
    turn (a recent one, a resurfacing one, …; the other's when one runs out),
    so a busy week doesn't push resurfacing off the first screen; then the
    rest of each, then the others by last activity."""
    def b(i):
        return blocks[i].get("block", blocks[i])
    act = {i: last_active(b(i)) or 0 for i in refs}
    recent = sorted((i for i in refs if now_min - act[i] <= RECENT_DAYS * 1440), key=lambda i: -act[i])
    mem = {i: memory(b(i), now_min) for i in refs if i not in set(recent)}
    total = lambda i: ((b(i).get("visits") or {}).get("total") or 0)
    faded = sorted((i for i, (s, r) in mem.items() if r < FADED_AT),
                   key=lambda i: -(1 - mem[i][1]) * (1 + total(i)) * mem[i][0] ** 0.5)[:RESURFACE]
    rest = sorted((i for i in refs if i not in set(recent) | set(faded)), key=lambda i: -act[i])
    r, f = [(i, "recent") for i in recent], [(i, "resurfacing") for i in faded]
    top = [x for pair in zip(r, f) for x in pair] + r[len(f):] + f[len(r):]
    return top[:TOP] + [x for x in r + f if x not in top[:TOP]] + [(i, "") for i in rest]


HITS_JUMP = 0.15   # randomized HITS's chance of a jump anywhere (Ng, Zheng & Jordan 2001), so sparse writing, in
HITS_ROUNDS = 100  # separate clusters, doesn't collapse onto one of them as plain HITS does


def pericope_edges(blocks: dict, refs: list) -> set:
    """(a, b): pericope `a` points at pericope `b`, a block in a quoting, linking to or paraphrasing a block of b
    (b itself or one inside it), a != b. A quote of a picture isn't pointing (it shows it, an illustration)."""
    tops, out = set(refs), set()
    for i, b in blocks.items():
        q = quoted(b)
        targets = ([q[0]] if q else []) + [x["to"] for x in links(b)] + ([paraphrases(b)] if paraphrases(b) else [])
        if not targets:
            continue
        a = home_of(blocks, i)[0]
        for t in targets:
            if t not in blocks or (q and t == q[0] and image_of(blocks[t])):
                continue
            h = t if t in tops else home_of(blocks, t)[0]
            if a in tops and h in tops and a != h:
                out.add((a, h))
    return out


def hits(refs: list, edges: set) -> tuple[dict, dict]:
    """Randomized HITS (Ng, Zheng & Jordan, "Stable algorithms for link analysis", 2001) over `edges`: ({ref: hub},
    {ref: authority}), each scaled so the average is 1. A hub points at good authorities (a way in: where to start);
    an authority is pointed at by good hubs (where you end up). Derived, never stored."""
    n = len(refs)
    if not n:
        return {}, {}
    outd, ind = {}, {}
    for a, b in edges:
        outd[a] = outd.get(a, 0) + 1
        ind[b] = ind.get(b, 0) + 1
    hub = {r: 1 / n for r in refs}
    auth = dict(hub)
    for _ in range(HITS_ROUNDS):
        auth = {r: HITS_JUMP / n for r in refs}
        for a, b in edges:
            auth[b] += (1 - HITS_JUMP) * hub[a] / outd[a]
        total = sum(auth.values())
        auth = {r: v / total for r, v in auth.items()}
        hub = {r: HITS_JUMP / n for r in refs}
        for a, b in edges:
            hub[a] += (1 - HITS_JUMP) * auth[b] / ind[b]
        total = sum(hub.values())
        hub = {r: v / total for r, v in hub.items()}
    return {r: v * n for r, v in hub.items()}, {r: v * n for r, v in auth.items()}


def alongside(edges: set, here: str) -> list[tuple[str, int]]:
    """The pericopes sitting with `here` in the structure, and how many ties each: pointed at by a pericope that
    points at `here` too (co-citation), or pointing at one `here` points at too (coupling); most ties first. Not
    `here`, nor what it points at or what points at it (those are tied to it directly)."""
    out_of = {}
    into = {}
    for a, b in edges:
        out_of.setdefault(a, set()).add(b)
        into.setdefault(b, set()).add(a)
    direct = out_of.get(here, set()) | into.get(here, set()) | {here}
    ties = {}
    for c in into.get(here, set()):                 # c points at here: what else does c point at
        for o in out_of.get(c, set()) - direct:
            ties[o] = ties.get(o, 0) + 1
    for t in out_of.get(here, set()):               # here points at t: what else points at t
        for o in into.get(t, set()) - direct:
            ties[o] = ties.get(o, 0) + 1
    return sorted(ties.items(), key=lambda x: (-x[1], x[0]))


NEXT_WITHIN = 30   # minutes: the next visit, if it begins this soon after one to `here` begins


def visited_next(blocks: dict, refs: list, here: str) -> list[tuple[str, int]]:
    """Where you went right after `here`: for each visit to `here` (the last ten it keeps), the pericope whose visit
    began next, within NEXT_WITHIN minutes (all of them, if several began that same minute); with how many of
    here's visits each followed, most first, then the latest."""
    theirs = {r: [m for m, _ in visits(blocks.get(r))] for r in refs if r != here}
    count, last = {}, {}
    for m in (m for m, _ in visits(blocks.get(here))):
        after = {r: min((v for v in vs if m < v <= m + NEXT_WITHIN), default=None) for r, vs in theirs.items()}
        soonest = min((v for v in after.values() if v is not None), default=None)
        for r, v in after.items():
            if v is not None and v == soonest:
                count[r] = count.get(r, 0) + 1
                last[r] = max(last.get(r, 0), v)
    out = [(r, count[r], last[r]) for r in count]
    return [(r, n) for r, n, _ in sorted(out, key=lambda x: (-x[1], -x[2]))]


def ago(minute: int | None, now_min: int) -> str:
    """'just now', '5m ago', '3h ago', '4d ago', '2mo ago', '1y ago'."""
    if minute is None:
        return ""
    d = max(now_min - minute, 0)
    for size, unit in ((525600, "y"), (43200, "mo"), (1440, "d"), (60, "h"), (1, "m")):
        if d >= size:
            return f"{d // size}{unit} ago"
    return "just now"


# --- kinds: what a block is (schema v16) ---------------------------------------
#
# A kind is a block (content Kind: {"kind": name, "blocks": its description}),
# a top-level pericope. A pericope (only a pericope)
# says what it is in `kinds`: {kind id: True | False}, only the answers you gave (yes, it's a poem; no, it isn't a letter).
# A model's guesses (a model outside fw writes its file beside the store)
# are kept apart, never stored: `guessed` keeps those that count, and they
# meet your answers in merge_kinds, where yours win.

GUESS_AT = 0.9  # a model's guess counts from this p(yes) up, and is applied (any model's, about anything)
MAYBE_AT = 0.5  # and from this one up it's a maybe, to review from the kind (maybes)

def kinds_of(b: dict | None) -> dict:
    """The answers given for block `b` (a store block or a library entry): {kind id: bool}."""
    b = b.get("block", b) if b else None
    return dict(b.get("kinds") or {}) if b else {}


def with_kinds(b: dict, answers: dict) -> dict:
    """Block `b` with these answers (a new block; none: no `kinds`)."""
    return {**b, "kinds": dict(answers)} if answers else without(b, "kinds")


def merge_kinds(answers: dict, guesses: dict | None = None) -> dict:
    """What a block is, all told: a model's guesses ({kind id: p}, as
    `guessed` gives them; a bool counts as 1 or 0), each at GUESS_AT or over
    a yes, under the answers given, which always win."""
    return {**{k: True for k, p in (guesses or {}).items() if p >= GUESS_AT}, **answers}


def guessed(data, blocks: dict, at: float = GUESS_AT) -> dict:
    """The guesses that count, {block id: {kind id: p}}, each block's kinds
    oldest first, out of a model's (`data`, kind-guesses.json as read:
    {guesses: {kind id: {block id: [p, kind's updated, block's updated]}}})
    and the blocks as they are now (the store's or the editor's library):
    only kinds that still exist, about pericopes that do (only a pericope
    has kinds), that the block has no
    answer about, still current (neither the kind nor the block changed
    since: both `updated` as the guess has them), and p at `at` (GUESS_AT)
    or over. Anything malformed counts for nothing."""
    block = lambda i: (lambda b: b.get("block", b) if isinstance(b, dict) else None)(blocks.get(i))
    per_kind = data.get("guesses") if isinstance(data, dict) else None
    out = {}
    for kid in sorted(per_kind) if isinstance(per_kind, dict) else []:
        k, said = block(kid), per_kind[kid]
        if kind_of(k) is None or not isinstance(said, dict):
            continue
        for bid, g in said.items():
            b = block(bid)
            match g:
                case [int() | float() as p, str() as ku, str() as bu] if (
                        b is not None and b.get("entry") and p >= at and kid not in kinds_of(b)
                        and ku == k.get("updated") and bu == b.get("updated")):
                    out.setdefault(bid, {})[kid] = p
    return out


def learned(data) -> set:
    """The kinds a model learned from the answers given (kind-guesses.json's
    `sources`: {kind id: {source: "learned", …}}): their guesses that count
    (`guessed`) are applied, drawn as a kind with a mark ("note·"), not asked
    as "note?"; still never stored. Anything malformed: none."""
    sources = data.get("sources") if isinstance(data, dict) else None
    return {k for k, v in sources.items() if isinstance(v, dict) and v.get("source") == "learned"} if isinstance(sources, dict) else set()


def is_applied(blocks: dict, bid: str, kid: str, learned_kinds) -> bool:
    """A guess that counts (`guessed`: GUESS_AT up) is applied, not asked,
    whichever model made it and whatever it's about, a pericope too (the
    user, 2026-11-18: "auto apply, no maybe, above a certain threshold").
    Only the unsure ones, MAYBE_AT up to GUESS_AT, are maybes to review.
    (The arguments stay for its callers.)"""
    return True


def maybes(data, blocks: dict, kid: str) -> list:
    """Kind `kid`'s maybes, to review: the pericopes a model guesses are one,
    unanswered and current (`guessed`, from MAYBE_AT up, so the unsure ones
    too), [(block id, p)], the likeliest first (then the oldest). Not
    guesses from GUESS_AT up (applied: is_applied)."""
    top = GUESS_AT
    entry = lambda i: (lambda b: isinstance(b, dict) and b.get("block", b).get("entry"))(blocks.get(i))
    found = [(i, g[kid]) for i, g in guessed(data, blocks, MAYBE_AT).items()
             if kid in g and i != kid and g[kid] < top and entry(i)]
    return sorted(found, key=lambda x: (-x[1], x[0]))


PROPOSE_AT = 5  # a kind a model proposes is offered while this many of its pericopes are still uncovered


def kind_cover(blocks: dict, data) -> set:
    """The pericopes some kind covers: a yes said, or a guess applied
    (`is_applied`; `data`: kind-guesses.json as read)."""
    blk = lambda b: b.get("block", b)
    out = {i for i, b in blocks.items() if True in kinds_of(blk(b)).values()}
    auto = learned(data)
    return out | {i for i, g in guessed(data, blocks).items() if any(is_applied(blocks, i, k, auto) for k in g)}


def open_proposals(data, blocks: dict, dismissed, covered: set) -> list:
    """The kinds a model proposes (kind-proposals.json, written beside the store by a model outside fw; `data`: {proposals:
    [{id, name, description, members, typical}]}) still worth offering, as
    given, each one's members now only the pericopes still here that no kind
    covers (`covered`, kind_cover's). Dropped: fewer than PROPOSE_AT left,
    a kind of that name now, or dismissed (kind-dismissed.json, `dismissed`:
    {dismissed: [{name, members}]}: the same name, case aside, or half the
    members or more in common). Anything malformed counts for nothing."""
    blk = lambda i: (lambda b: b.get("block", b) if isinstance(b, dict) else None)(blocks.get(i))
    said = dismissed.get("dismissed") if isinstance(dismissed, dict) else None
    said = [d for d in said if isinstance(d, dict)] if isinstance(said, list) else []
    def alike(d, name, members):
        theirs, ours = set(d.get("members") or []), set(members)
        return same_name(str(d.get("name") or ""), name) or len(theirs & ours) * 2 >= max(len(theirs | ours), 1)
    out = []
    for p in (data.get("proposals") if isinstance(data, dict) else None) or []:
        match p:
            case {"name": str(name), "members": list(members)} if tidy_name(name):
                pass
            case _:
                continue
        here = [m for m in members if isinstance(m, str) and (blk(m) or {}).get("entry") and m not in covered]
        if len(here) < PROPOSE_AT or kind_named(blocks, name) is not None or any(alike(d, name, members) for d in said):
            continue
        out.append({**p, "name": tidy_name(name), "members": here,
                    "typical": [t for t in p.get("typical") or [] if isinstance(t, str) and blk(t) is not None],
                    "description": str(p.get("description") or "")})
    return out


def merge_answers(a: dict, b: dict, base: dict | None = None) -> dict:
    """Two copies of a block's answers made one (when syncing two stores), kind by kind:
    what one side changed since `base` (the copy both came from) is kept,
    and where both changed it differently, `a`'s (the side kept)."""
    base = base or {}
    out = {}
    for k in [*a, *(k for k in b if k not in a), *(k for k in base if k not in a and k not in b)]:
        x, y, z = a.get(k), b.get(k), base.get(k)
        v = x if x == y or y == z else y if x == z else x
        if v is not None:
            out[k] = v
    return out


def kind_ids(blocks: dict) -> list:
    """The kinds (the blocks whose content is a Kind), oldest first. Works
    on the store's blocks or the editor's library alike."""
    return sorted(i for i, b in blocks.items() if kind_of(b.get("block", b)) is not None)


def tidy_name(name: str) -> str:
    """A kind's name as it's kept: its spacing tidied."""
    return " ".join(name.split())


def same_name(a: str, b: str) -> bool:
    """Two kinds' names are the same one: case and spacing aside."""
    return tidy_name(a).casefold() == tidy_name(b).casefold()


def kind_named(blocks: dict, name: str) -> str | None:
    """The kind called `name` (case and spacing aside), else None."""
    return next((i for i in kind_ids(blocks) if same_name(kind_of(blocks[i].get("block", blocks[i])), name)), None)


def of_kind(blocks: dict, kid: str, guesses: dict | None = None) -> list:
    """The blocks that are kind `kid` (by merge_kinds: your answers, over a
    model's guesses, {block id: {kind id: p}} as `guessed` gives them), oldest first."""
    guesses = guesses or {}
    return sorted(i for i, b in blocks.items() if merge_kinds(kinds_of(b), guesses.get(i)).get(kid) is True)


NOT = "not "  # in the header's kinds: "poem, not letter"


def parse_kinds(text: str) -> list:
    """The header's kinds field -> [(name, yes)], in order, each name once
    (the last word on it wins): commas apart, "not " before a no."""
    out = {}
    for part in text.split(","):
        name = " ".join(part.split())
        yes = not name.casefold().startswith(NOT)
        name = name if yes else " ".join(name[len(NOT):].split())
        if name:
            out = {k: v for k, v in out.items() if not same_name(k, name)} | {name: yes}
    return list(out.items())


def kinds_text(blocks: dict, b: dict | None) -> str:
    """Block `b`'s answers as the header shows them: "poem, not letter"
    (kinds that are gone left out)."""
    name_of = lambda i: kind_of(blocks[i].get("block", blocks[i])) if i in blocks else None
    return ", ".join(("" if yes else NOT) + name_of(k) for k, yes in kinds_of(b).items() if name_of(k))
