"""What a block shows: its text, its items (quotes seen through their masks), its draft, its title."""

from __future__ import annotations

import json

from fw.block.case import children, expr_of, image_of, index, kind_of, merge_inner, quote_inner, quote_show, quoted, text_of
from fw.block.text import EXPR_REF, INLINE_CODE, derive_title
from fw.block.tree import ancestors, flat, fold, subtree
from fw.draft import BLOCK_RE, IMAGE_RE, QUOTE_RE, block_line, draft_digest, expr_line, image_line, parse_draft, quote_line
from fw.lens import ELLIPSIS, intersect, view


def named_refs(blocks: dict, src: str, seen: frozenset = frozenset()) -> str:
    """Code `src` with each @reference as its target's title ("?" for one that's gone)."""
    def named(m):
        r = blocks.get(m.group(1))
        return "?" if r is None else (kind_of(r) or r.get("title") or derive_title(own_text(blocks, m.group(1), seen))
                                      or "(untitled)")
    return EXPR_REF.sub(named, src)


def readable(blocks: dict, text: str, seen: frozenset = frozenset()) -> str:
    """A stored text as a title reads it: each inline expression its code, references named; `\\$` a dollar."""
    return INLINE_CODE.sub(lambda m: named_refs(blocks, m.group(1), seen), text).replace("\\$", "$")


def own_text(blocks: dict, ref: str, seen: frozenset = frozenset()) -> str:
    """A block's own text, or its children's in order (an expression's: its code); quotes and images have none."""
    def leaf(b, i, seen):
        return text_of(b) if text_of(b) is not None else named_refs(blocks, expr_of(b), seen | {i}) if expr_of(b) is not None else ""
    skip = lambda k: False if quoted(blocks.get(k)) or image_of(blocks.get(k)) else None
    return fold(blocks, ref, leaf, lambda parts: "\n".join(p for p in parts if p is not False), skip, seen)


def seen_quote(blocks: dict, qid: str, inner: dict) -> tuple:
    """Quote `qid` seen through quotes whose inner masks are `inner`: ("quote", target, its mask narrowed by theirs,
    show, the inner masks in force inside it)."""
    b = blocks.get(qid)
    target, mask = quoted(b)
    return ("quote", target, intersect(mask, inner.get(qid)), quote_show(b), merge_inner(inner, quote_inner(b)))


def block_items(blocks: dict, ref: str, seen: frozenset = frozenset(), inner: dict | None = None) -> list:
    """What a block shows, in order: ("text", text), ("quote", target, mask, show, inner) seen through `inner`,
    ("image", id), ("expr", id). A quote shows its view (text keeps its ELLIPSIS marks)."""
    inner = inner or {}
    def leaf(b, i, seen):
        if (t := text_of(b)) is not None:
            return [("text", t)]
        if quoted(b):
            _, target, mask, _, deeper = seen_quote(blocks, i, inner)
            return quote_items(blocks, target, mask, seen | {i}, deeper)
        return [("image", i)] if image_of(b) is not None else []
    def atom(k):
        b = blocks.get(k)
        return ([seen_quote(blocks, k, inner)] if quoted(b) else [("image", k)] if image_of(b)
                else [("expr", k)] if expr_of(b) is not None else None)
    return flat(blocks, ref, leaf, atom, seen)


def quote_items(blocks: dict, ref: str, mask: list | None, seen: frozenset = frozenset(),
                inner: dict | None = None) -> list:
    """What a quote of `ref` shows: its items, or with a mask, its view's (text keeps its ELLIPSIS marks)."""
    inner = inner or {}
    if mask is None or ref not in blocks:
        return block_items(blocks, ref, seen, inner)
    items, last = [], None
    for line, bid in zip(*parse_draft(view(block_draft(blocks, ref), mask))):
        m = QUOTE_RE.fullmatch(line)
        if image := IMAGE_RE.fullmatch(line):
            items.append(("image", image.group(1)))
        elif m:
            items.append(seen_quote(blocks, m.group(2), inner) if m.group(2) and quoted(blocks.get(m.group(2)))
                         else ("quote", m.group(1), None, [], inner))
        elif items and items[-1][0] == "text" and bid == last:
            items[-1] = ("text", items[-1][1] + "\n" + line)
        else:
            items.append(("text", line))
        last = bid
    return items


def items_text(blocks: dict, items: list, seen: set, own: bool = True) -> str:
    """`items` as text, each quote's flattened in; a block already in `seen` left out. own=False: only quoted text."""
    parts = []
    for item in items:
        match item:
            case ("text", text) if own:
                parts.append(text.replace(ELLIPSIS, ""))
            case ("quote", target, mask, _, inner) if target in blocks and target not in seen:
                seen.add(target)
                parts.append(items_text(blocks, quote_items(blocks, target, mask, inner=inner), seen))
    return "\n".join(p for p in parts if p)


def full_text(blocks: dict, ref: str, own: bool = True) -> str:
    """Everything a block shows as text: its own, then what it quotes, flattened."""
    return items_text(blocks, block_items(blocks, ref), {ref}, own) if ref in blocks else ""


def shown_text(blocks: dict, ref: str) -> str:
    """What a block shows as plain text, quotes flattened in, each hidden stretch "…" (a quote detached)."""
    parts = []
    for item in block_items(blocks, ref):
        match item:
            case ("text", text):
                parts.append(text.replace(ELLIPSIS, "…"))
            case ("quote", target, mask, _, inner) if target in blocks:
                parts.append(items_text(blocks, quote_items(blocks, target, mask, inner=inner), {ref, target}))
    return "\n".join(p for p in parts if p)


# --- the draft: a block as plain text, each child's text after a marker line naming it ---

def block_draft(blocks: dict, ref: str) -> str:
    """A block as its draft: each child after its marker line, each quote, image or expression one line, a container's
    children naming it too, to any depth. A quote is drafted where it's quoted."""
    b = blocks[ref]
    return text_of(b) if text_of(b) is not None else "\n".join(child_lines(blocks, children(b)))


def child_lines(blocks: dict, kids: list, within: tuple = ()) -> list:
    """The draft lines of children `kids` (in the containers `within`, innermost first)."""
    out = []
    for k in kids:
        b = blocks.get(k)
        if q := quoted(b):
            out.append(quote_line(q[0], k, within))
        elif image_of(b):
            out.append(image_line(k, within))
        elif expr_of(b) is not None:
            out.append(expr_line(k, expr_of(b), within))
        elif children(b) and k not in within:
            out += child_lines(blocks, children(b), (k, *within))
        elif b is not None:
            out += [block_line(k, within), own_text(blocks, k)]
    return out


def regions(blocks: dict, ref: str, draft: str) -> list:
    """Where each block of `ref`'s draft is: (id, start, end, whether it's one line: a quote or an image)."""
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


def home_of(blocks: dict, ref: str) -> tuple:
    """(the entry `ref` is in, where it starts in that entry's draft); an entry is its own; in none, (None, 0)."""
    if blocks.get(ref, {}).get("entry"):
        return ref, 0
    home = next((i for i in ancestors(blocks, ref) if blocks[i].get("entry")), None)
    if home is None:
        return None, 0
    inside = set(subtree(blocks, ref))
    return home, next((s for i, s, _, _ in regions(blocks, home, block_draft(blocks, home)) if i in inside), 0)


def content_hash(blocks: dict, ref: str) -> str | None:
    """A fingerprint of what a block shows (text, split, quotes and masks, expressions' code; not ids): the `base` an
    editor's text was built on, so a commit can tell it changed elsewhere."""
    if ref not in blocks:
        return None
    code = lambda i: ("expr", i, expr_of(blocks.get(i)))
    items = [code(it[1]) if it[0] == "expr" else it for it in block_items(blocks, ref)]
    return draft_digest(json.dumps(items if expr_of(blocks[ref]) is None else [code(ref)]))


def display_title(blocks: dict, ref: str, named: dict | None = None) -> str | None:
    """A kind's name, the written title, one derived from the first line, a picture's title from a model (`named`,
    {file: title}), else "picture" if it shows one."""
    b = blocks[ref]
    return (kind_of(b) or b.get("title") or derive_title(readable(blocks, own_text(blocks, ref), frozenset({ref})))
            or (named or {}).get(image_of(b))
            or ("picture" if any(item[0] == "image" for item in block_items(blocks, ref)) else None))


def is_empty_untitled(blocks: dict, ref: str) -> bool:
    """No text, title, quotes or images, anywhere in it (a kind never is: it has its name)."""
    b = blocks[ref]
    return (kind_of(b) is None and not own_text(blocks, ref).strip() and not b.get("title")
            and not any(item[0] in ("quote", "image") for item in block_items(blocks, ref)))


def build_library(data: dict, named: dict | None = None) -> dict:
    """Every block by id with its display title: {title, words, content, entry, block}."""
    blocks = index(data)
    return {i: {"title": display_title(blocks, i, named) or "untitled", "words": b.get("words", 0),
                "content": b.get("content", ""), "entry": bool(b.get("entry")), "block": b} for i, b in blocks.items()}
