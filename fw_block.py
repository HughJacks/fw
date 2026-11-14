"""fw_block — the block type: taking blocks apart, their text, titles and
counts. Pure functions over the store's blocks (by id); no files.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from fw_draft import BLOCK_RE, IMAGE_RE, QUOTE_RE, block_line, draft_digest, image_line, is_atom, parse_draft, quote_line
from fw_lens import ELLIPSIS, intersect, normalize, spans_of, view

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
#   Quote   {"quote": "<id>", "mask": [ … ], "show": [ … ], "inner": {"<quote id>": [ … ]}}
#                                               a live view of another block; `show`: which of
#                                               its properties its box's top line shows; `inner`:
#                                               masks of the quotes inside what it shows, seen
#                                               through it (each only hides more)
#
# The functions below take a block apart by which of these it is (match).
# A mask, as the code works with it, is anchors into the target's draft
# (fw_lens); on disk it's per block (masks_out, masks_in).

def children(b: dict | None) -> list:
    """A Blocks block's children (ids), else none."""
    match b.get("content") if b else None:
        case list(kids):
            return kids
    return []


def quoted(b: dict | None) -> tuple | None:
    """A Quote block's (target id, mask or None), else None."""
    match b.get("content") if b else None:
        case {"quote": str(target), **rest}:
            return target, rest.get("mask")
    return None


MAX_DEPTH = 3  # quotes inside quotes inside quotes; deeper ones show as one "⋯" line

SHOWABLE = ("title", "created", "updated", "words")  # what a quote's top line can show, in this order


def is_whole(b: dict | None) -> bool:
    """A block that's one thing whole, with no text to write in (an image;
    any such case added later goes here too): selected whole, never gone
    into, even through a quote of it."""
    return image_of(b) is not None


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
    """The block `b` is marked as a paraphrase of, if any."""
    b = b.get("block", b) if b else None
    return b.get("paraphrases") if b else None


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


def with_links(b: dict, ls: list) -> None:
    """Give block `b` these hyperlinks (none: no `links`)."""
    if ls:
        b["links"] = ls
    else:
        b.pop("links", None)


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
        case str(text):
            return text
        case list(kids):
            return "\n".join(own_text(blocks, k, seen | {ref}) for k in kids
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
        case str(text):
            return [("text", text)]
        case list(kids):
            out = []
            for k in kids:
                if quoted(blocks.get(k)):
                    out.append(seen_quote(blocks, k, inner))
                elif image_of(blocks.get(k)):
                    out.append(("image", k))
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
        case str(text):
            return text
        case list(kids):
            return "\n".join(child_lines(blocks, kids))
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


def with_mask(b: dict, mask: list | None) -> None:
    """Give Quote block `b` a new mask (None: show all of it); the rest of it stays."""
    rest = {k: v for k, v in b["content"].items() if k != "mask"}
    b["content"] = {**rest, "mask": mask} if mask is not None else rest


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
    if isinstance(blocks[ref].get("content"), str):
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
    reaches, and each block marked as a paraphrase of it. Each a dict: kind
    ("quote", "masked quote", "link", "paraphrase"), `by` (the
    pointing block), `home` and `at` (the entry it's in, and where in that
    entry's draft, as home_of), `created` (a quote's block's; a link's own,
    None before links were dated)."""
    out = []
    for i, b in blocks.items():
        q = quoted(b)
        points = [("masked quote" if q[1] is not None else "quote", b.get("created"), 0)] if q and q[0] == ref else []
        points += [("link", link.get("created"), link["at"][0]) for link in links(b) if link["to"] == ref]
        points += [("paraphrase", b.get("created"), 0)] if paraphrases(b) == ref else []
        if not points:
            continue
        home, start = home_of(blocks, i)
        if home is None:
            continue  # (loose: held only by the clipboard, or about to be erased)
        out += [{"kind": k, "by": i, "home": home, "at": start + off, "created": c} for k, c, off in points]
    return sorted(out, key=lambda x: (x["created"] or "", x["by"]))


def backlink_summary(found: list) -> str:
    """e.g. "3 · 1 quote, 1 masked quote, 1 link", or "none"."""
    if not found:
        return "none"
    kinds = [k for k in ("quote", "masked quote", "link", "paraphrase") if any(x["kind"] == k for x in found)]
    counts = [f"{sum(x['kind'] == k for x in found)} {k}{'s' if sum(x['kind'] == k for x in found) > 1 else ''}" for k in kinds]
    return f"{len(found)} · " + ", ".join(counts)


def families(blocks: dict) -> dict:
    """The paraphrase families: the blocks joined by `paraphrases` marks (a
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
                   if a < b and (max(a, s) < min(b, e) or s == e and a <= s and e <= b)]
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
    return normalize(draft, [x for span in merged for x in span])


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


def with_inner(b: dict, inner: dict) -> None:
    """Give Quote block `b` new masks for the quotes inside it (none: no `inner`)."""
    rest = {k: v for k, v in b["content"].items() if k != "inner"}
    b["content"] = {**rest, "inner": inner} if inner else rest


def with_show(b: dict, show: list) -> None:
    """Choose what Quote block `b`'s top line shows (none: no `show`)."""
    rest = {k: v for k, v in b["content"].items() if k != "show"}
    b["content"] = {**rest, "show": [k for k in SHOWABLE if k in show]} if show else rest


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
    """No text, no written title and no quotes or images: nothing worth keeping."""
    b = blocks[ref]
    return (not own_text(blocks, ref).strip() and not b.get("title")
            and not any(item[0] in ("quote", "image") for item in block_items(blocks, ref)))  # (one nested in a child too)


def display_title(blocks: dict, ref: str) -> str | None:
    """The written title, else one derived from the first line, else from
    what else it holds ("picture", for a block with no text but a picture)."""
    return (blocks[ref].get("title") or derive_title(own_text(blocks, ref))
            or ("picture" if any(item[0] == "image" for item in block_items(blocks, ref)) else None))


def entry_ids(data: dict) -> list[str]:
    """The entries: the top-level blocks, the ones marked `entry`."""
    return [b["id"] for b in data["blocks"] if b.get("entry")]


def build_library(data: dict) -> dict:
    """Every block by id, as the editor needs it to draw quotes and fill the / menu."""
    blocks = index(data)
    return {i: {"title": display_title(blocks, i) or "untitled", "words": b.get("words", 0),
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


def with_visits(b: dict, v: dict | None) -> None:
    """Give block `b` visits `v` (None: none)."""
    if v:
        b["visits"] = v
    else:
        b.pop("visits", None)


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
