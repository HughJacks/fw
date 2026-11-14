"""fw_draft — a block as the plain text the editor edits (the draft), and ids.

Pure functions: no files, no store. In the draft each child's text follows a
marker line naming it, and each quote is one line naming its target and
itself; the editor hides the markers. An image (a block that is one picture) is one
line too, naming itself. A child of a block inside the entry (a
container: a block holding blocks of its own) names the containers it's in
too, innermost first, and the editor keeps them in a `nest` map (child id ->
the container it's in, at every level).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime

# In the editor's plain-text draft a quote is one line of its own, and each
# child's text follows a marker line naming it (the editor hides those).
_ID = r"[0-9]{8}T[0-9]{6}-[0-9a-f]{4}"
QUOTE_RE = re.compile(rf"\{{\{{quote ({_ID})(?: ({_ID}))?((?: {_ID})*)\}}\}}")  # target, quote id, its containers


BLOCK_RE = re.compile(rf"\{{\{{block(?: ({_ID}))?((?: {_ID})*)\}}\}}")  # id, its containers
IMAGE_RE = re.compile(rf"\{{\{{image ({_ID})((?: {_ID})*)\}}\}}")  # the image block, its containers


def is_atom(line: str) -> bool:
    """A line that's one block whole, not text: a quote's, or an image's."""
    return bool(QUOTE_RE.fullmatch(line) or IMAGE_RE.fullmatch(line))


def atom_id(line: str) -> str | None:
    """The block a quote or image line is (a quote's own id, not its target's)."""
    m = QUOTE_RE.fullmatch(line)
    if m:
        return m.group(2)
    m = IMAGE_RE.fullmatch(line)
    return m.group(1) if m else None


def quote_line(ref: str, qid: str | None = None, within: tuple = ()) -> str:
    """A quote of block `ref` in the draft; `qid` names the Quote block itself
    (where its mask lives), `within` the containers it's in, innermost first."""
    return "{{quote " + ref + (" " + qid if qid else "") + "".join(" " + c for c in within if qid) + "}}"


def image_line(ref: str, within: tuple = ()) -> str:
    """Image block `ref` in the draft (in the containers `within`, innermost first)."""
    return "{{image " + ref + "".join(" " + c for c in within) + "}}"


def block_line(ref: str, within: tuple = ()) -> str:
    return "{{block " + ref + "".join(" " + c for c in within) + "}}"


def chain(nest: dict, key) -> tuple:
    """The containers `key` is in, by `nest` (child -> container), innermost first."""
    out, c = [], nest.get(key)
    while c and c != key and c not in out:
        out.append(c)
        c = nest.get(c)
    return tuple(out)


def now_local() -> datetime:
    return datetime.now().astimezone()


def gen_id(created: datetime) -> str:
    return created.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:4]


def new_id(taken, created: datetime | None = None) -> str:
    """A fresh id, not one of `taken`."""
    while True:
        i = gen_id(created or now_local())
        if i not in taken:
            return i


def draft_place(draft: str, p: int) -> tuple[int, int]:
    """Offset `p` in a draft -> (line, column) as the editor shows it, with
    the marker lines hidden."""
    before = draft[:p].split("\n")
    return sum(not BLOCK_RE.fullmatch(l) for l in before[:-1]), len(before[-1])


def parse_draft(text: str, taken=()) -> tuple[list, list]:
    """The editor's plain text -> the lines it shows, and for each line the id
    of the block it's part of (None on a quote or image line). Text with no marker of
    its own (typed below a quote, or after a bare {{block}}) is a new block,
    given a fresh id that isn't one of `taken`."""
    lines, bids, cur, seen = [], [], None, set()
    def fresh():
        i = new_id(set(taken) | seen)
        seen.add(i)
        return i
    for line in text.split("\n"):
        m = BLOCK_RE.fullmatch(line)
        if m:
            cur = m.group(1) if m.group(1) and m.group(1) not in seen else fresh()
            seen.add(cur)
        elif m := QUOTE_RE.fullmatch(line):
            lines.append(quote_line(m.group(1), m.group(2)))  # in the buffer, just what it quotes and its id
            bids.append(None)
            cur = None
        elif m := IMAGE_RE.fullmatch(line):
            lines.append(image_line(m.group(1)))  # in the buffer, just its id
            bids.append(None)
            cur = None
        else:
            cur = cur or fresh()
            lines.append(line)
            bids.append(cur)
    return (lines, bids) if lines else ([""], [fresh()])


def parse_nest(text: str) -> dict:
    """The draft's nesting: each nested child's id -> the block it's in, and
    each container's -> the one it's in."""
    nest = {}
    for line in text.split("\n"):
        if m := BLOCK_RE.fullmatch(line):
            key, path = m.group(1), m.group(2).split()
        elif m := QUOTE_RE.fullmatch(line):
            key, path = m.group(2), m.group(3).split()
        elif m := IMAGE_RE.fullmatch(line):
            key, path = m.group(1), m.group(2).split()
        else:
            continue
        if key and path:
            for child, container in zip([key, *path], path):
                nest[child] = container
    return nest


def format_draft(lines: list, bids: list, silent=(), nest=None) -> str:
    """The inverse of parse_draft (and parse_nest): a marker line before each
    block's text (except a `silent` one, whose marker is out of sight in a
    masked view), naming the block it's nested in, as each quote does."""
    nest = nest or {}
    out, prev = [], None
    for line, bid in zip(lines, bids):
        if bid is not None and bid != prev and bid not in silent:
            out.append(block_line(bid, chain(nest, bid)))
        out.append(atom_draft(line, nest) if bid is None else line)
        prev = bid
    return "\n".join(out)


def atom_draft(line: str, nest: dict) -> str:
    """A buffer's quote or image line as the draft has it: naming its containers."""
    if m := QUOTE_RE.fullmatch(line):
        return quote_line(m.group(1), m.group(2), chain(nest, m.group(2))) if m.group(2) else line
    if m := IMAGE_RE.fullmatch(line):
        return image_line(m.group(1), chain(nest, m.group(1)))
    return line


def draft_items(text: str, taken=(), keep=frozenset()) -> list:
    """The editor's plain text -> a block's content, in order: ("text", id,
    text) per child, ("quote", target, quote id) per quote, ("image", id)
    per image, and ("blocks",
    id, items) for a block with children of its own (a container), its
    children's items in it, to any depth. Blank lines at the edges of a child are just
    spacing (like the room fw leaves to write in when it opens an entry), so
    they're trimmed, and a child of only blank lines is left out, unless
    it's one of `keep` (a paraphrase not yet written: its mark is kept), or
    in one of `keep` that holds nothing else (so it isn't lost)."""
    lines, bids = parse_draft(text, taken)
    nest = parse_nest(text)
    runs = []  # (the containers it's in, outermost first, item)
    for line, bid in zip(lines, bids):
        if bid is None and (m := IMAGE_RE.fullmatch(line)):
            runs.append((chain(nest, m.group(1))[::-1], ["image", m.group(1)]))
        elif bid is None:
            m = QUOTE_RE.fullmatch(line)
            runs.append((chain(nest, m.group(2))[::-1], ["quote", m.group(1), m.group(2)]))
        elif runs and runs[-1][1][0] == "text" and runs[-1][1][1] == bid:
            runs[-1][1][2].append(line)
        else:
            runs.append((chain(nest, bid)[::-1], ["text", bid, [line]]))
    items = []
    written = {c for path, run in runs if run[0] != "text" or trim_edges(run[2]) for c in path}
    for path, run in runs:
        if run[0] == "text":
            body = trim_edges(run[2])
            if not body and run[1] not in keep and not any(c in keep and c not in written for c in path):
                continue  # (kept: a paraphrase's own, or the blank blocks holding one up that has nothing else)
            item = ("text", run[1], "\n".join(body))
        else:
            item = tuple(run)
        level = items
        for c in path:  # into its containers: the one just before, if it's the same, else a new one
            if not (level and level[-1][0] == "blocks" and level[-1][1] == c):
                level.append(("blocks", c, []))
            level = level[-1][2]
        level.append(item)
    return items


def trim_edges(lines: list) -> list:
    """`lines` without the blank (or whitespace-only) lines at either end."""
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def draft_digest(draft: str) -> str:
    return hashlib.sha1(draft.encode("utf-8")).hexdigest()
