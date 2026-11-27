"""The block type: a block is {id, title, created, words, content, …} and its content one case of

    Text        "a string"
    Blocks      ["<id>", …]                                 its children, in order
    Quote       {"quote": id, "mask"?, "show"?, "inner"?, "lock"?}
                                                            a live view of another block
    Paraphrase  {"paraphrase": id, "text": "…"}             another block said again
    Image       {"image": "<file>"}                         one picture
    Kind        {"kind": name, "blocks": [id, …]}           a tag, described by its child blocks
    Expression  {"expr": "<source>"}                        a program the page evaluates

Each accessor takes a block apart by its case (None/[] for the others); each `with_*` makes a new block.
A library entry ({…, "block": b}) unwraps to its block where noted.
"""

from __future__ import annotations

from fw.block.text import EXPR_REF, inline_codes
from fw.lens import intersect, shown_only

MAX_DEPTH = 3   # quotes inside quotes inside quotes; deeper ones show as one "⋯" line
SHOWABLE = ("title", "created", "updated", "words")   # what a quote's top line can show, in this order


def index(data: dict) -> dict:
    """Every block by id."""
    return {b.get("id"): b for b in data["blocks"]}


def unwrap(b):
    """A library entry's block (a store block as it is)."""
    return b.get("block", b) if isinstance(b, dict) and b else None


def content(b: dict | None):
    return b.get("content") if b else None


def children(b: dict | None) -> list:
    """A Blocks block's children, or a Kind's description; else none."""
    match content(b):
        case list(kids) | {"kind": str(), "blocks": list(kids)}:
            return kids
    return []


def holds(b: dict | None) -> bool:
    """Whether `b` holds blocks (Blocks or Kind), even none."""
    match content(b):
        case list() | {"kind": str(), "blocks": list()}:
            return True
    return False


def kind_of(b: dict | None) -> str | None:
    """A Kind block's name."""
    match content(b):
        case {"kind": str(name), "blocks": list()}:
            return name
    return None


def text_of(b: dict | None) -> str | None:
    """A block of text's own text: a Text's string, a Paraphrase's words."""
    match content(b):
        case str(text) | {"paraphrase": str(), "text": str(text)}:
            return text
    return None


def paraphrases(b: dict | None) -> str | None:
    """What a Paraphrase block paraphrases (unwraps)."""
    match content(unwrap(b)):
        case {"paraphrase": str(src), "text": str()}:
            return src
    return None


def image_of(b: dict | None) -> str | None:
    """An Image block's file name."""
    match content(b):
        case {"image": str(name)}:
            return name
    return None


def expr_of(b: dict | None) -> str | None:
    """An Expression block's source."""
    match content(b):
        case {"expr": str(src)}:
            return src
    return None


def _quote(b: dict | None) -> dict | None:
    match content(b):
        case {"quote": str()} as c:
            return c
    return None


def block_type(b: dict | None) -> str:
    """The case's name: text, paraphrase, image, kind, quote, expression, else "block"."""
    match content(b):
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
    """The header's type: "tag: poem" for a kind; with `blocks`, a pericope of one block is that block's type,
    else "pericope"."""
    if kind_of(b) is not None:
        return f"tag: {kind_of(b)}"
    if blocks is None or not (b or {}).get("entry") or block_type(b) != "block":
        return block_type(b)
    kids = [k for k in children(b) if k in blocks]
    one = block_type(blocks[kids[0]]) if len(kids) == 1 else "block"
    return one if one != "block" else "pericope"


def is_whole(b: dict | None) -> bool:
    """A block with nothing to write in (an image)."""
    return image_of(b) is not None


def quoted(b: dict | None) -> tuple | None:
    """A Quote's (target, mask as it shows, without its empty places)."""
    c = _quote(b)
    return (c["quote"], shown_only(c.get("mask"))) if c else None


def raw_mask(b: dict | None) -> list | None:
    """A Quote's mask with its empty places."""
    return (_quote(b) or {}).get("mask")


def quote_show(b: dict | None) -> list:
    """What a Quote's top line shows."""
    show = (_quote(b) or {}).get("show")
    return [k for k in SHOWABLE if k in show] if isinstance(show, list) else []


def quote_lock(b: dict | None) -> bool:
    """Whether a Quote is locked: nothing written through it."""
    return (_quote(b) or {}).get("lock") is True


def quote_inner(b: dict | None) -> dict:
    """A Quote's masks for the quotes inside what it shows, by quote id."""
    inner = (_quote(b) or {}).get("inner")
    return inner if isinstance(inner, dict) else {}


def links(b: dict | None) -> list:
    """A block's hyperlinks: [{"to": entry id, "at": [start, end]}] on its text."""
    return list(b.get("links", [])) if b else []


def expr_refs(b: dict | None) -> list:
    """The blocks an expression's source, or a text's inline expressions, refer to (`@<id>`), each once, in order."""
    found = EXPR_REF.findall("\n".join([expr_of(b) or "", *inline_codes(text_of(b) or "")]))
    return list(dict.fromkeys(found))


def locked_by(blocks: dict, path: list) -> str | None:
    """The outermost locked quote on `path` (the quotes open from the pericope inward), else None: you can write."""
    return next((q for q in path if quote_lock(blocks.get(q))), None)


def merge_inner(a: dict, b: dict) -> dict:
    """Two quotes' inner masks, one seen through the other: both narrow."""
    return {**a, **b, **{k: intersect(a[k], b[k]) for k in a.keys() & b.keys()}}


# --- new blocks --------------------------------------------------------------------

def without(b: dict, key: str) -> dict:
    """Block `b` without field `key`."""
    return {k: v for k, v in b.items() if k != key}


def _field(b: dict, key: str, value, keep: bool) -> dict:
    return {**b, key: value} if keep else without(b, key)


def _quote_field(b: dict, key: str, value, keep: bool) -> dict:
    return {**b, "content": _field(b["content"], key, value, keep)}


def with_children(b: dict, kids: list) -> dict:
    """A Kind keeps its name; anything else becomes Blocks."""
    name = kind_of(b)
    return {**b, "content": {"kind": name, "blocks": kids} if name is not None else kids}


def with_text(b: dict, text: str) -> dict:
    """A paraphrase stays one, of the same original; anything else becomes Text."""
    src = paraphrases(b)
    return {**b, "content": {"paraphrase": src, "text": text} if src else text}


def with_links(b: dict, ls: list) -> dict:
    return _field(b, "links", ls, bool(ls))


def with_mask(b: dict, mask: list | None) -> dict:
    """None: show all of it."""
    return _quote_field(b, "mask", mask, mask is not None)


def with_inner(b: dict, inner: dict) -> dict:
    return _quote_field(b, "inner", inner, bool(inner))


def with_show(b: dict, show: list) -> dict:
    return _quote_field(b, "show", [k for k in SHOWABLE if k in show], bool(show))


def with_lock(b: dict, on: bool) -> dict:
    return _quote_field(b, "lock", True, bool(on))


def with_visits(b: dict, v: dict | None) -> dict:
    return _field(b, "visits", v, bool(v))


def with_kinds(b: dict, answers: dict) -> dict:
    return _field(b, "kinds", dict(answers), bool(answers))
