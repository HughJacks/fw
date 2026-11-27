"""Walking the blocks: one closure (`reach`) and one fold (`fold`, `flat`) over the content cases, and what they give."""

from __future__ import annotations

import hashlib

from fw.block.case import children, holds, image_of, paraphrases, unwrap


def reach(start: list, step, ok=lambda i: True) -> list:
    """Every id reachable from `start` by `step(id) -> ids`, each once, depth first, those `ok` only (and walked on
    from)."""
    out, todo = [], list(start)
    while todo:
        i = todo.pop()
        if i not in out and ok(i):
            out.append(i)
            todo += step(i)
    return out


def fold(blocks: dict, ref: str, leaf, join, atom=lambda k: None, seen: frozenset = frozenset()):
    """Block `ref` folded: a block that holds blocks joins (`join`) what each child gives, `atom(k)`, or folded if
    that's None; anything else is `leaf(b, ref, seen)`, b None for a block gone or met again inside itself."""
    b = blocks.get(ref)
    if b is None or ref in seen:
        return leaf(None, ref, seen)
    if not holds(b):
        return leaf(b, ref, seen)
    seen = seen | {ref}
    return join([(lambda a: a if a is not None else fold(blocks, k, leaf, join, atom, seen))(atom(k)) for k in children(b)])


def flat(blocks: dict, ref: str, leaf, atom=lambda k: None, seen: frozenset = frozenset()) -> list:
    """`fold` into one list: each leaf and atom gives a list."""
    return fold(blocks, ref, leaf, lambda parts: [x for p in parts for x in p], atom, seen)


def parents(blocks: dict, ref: str) -> list:
    return [i for i, b in blocks.items() if ref in children(b)]


def held(blocks: dict) -> set:
    """Every block some block holds as a child."""
    return {k for b in blocks.values() for k in children(b)}


def loose(blocks: dict, ref: str, holders: set | None = None) -> bool:
    """A block nothing holds that isn't an entry (put back by an undo, or pasted, before its holder is saved).
    `holders`: held(blocks), when asking about many."""
    b = blocks.get(ref)
    return b is not None and not b.get("entry") and ref not in (held(blocks) if holders is None else holders)


def subtree(blocks: dict, ref: str) -> list:
    """`ref` and every block under it (not what it quotes); store blocks or library alike."""
    return reach([ref], lambda i: children(unwrap(blocks.get(i))), lambda i: unwrap(blocks.get(i)) is not None)


def ancestors(blocks: dict, ref: str) -> list:
    """Every block `ref` is inside, up to the entries."""
    return reach(parents(blocks, ref), lambda i: parents(blocks, i), lambda i: i != ref)


def families(blocks: dict) -> dict:
    """The paraphrase families ({member: [every member, oldest first]}, families of two or more); store or library."""
    near = {}
    for i, b in blocks.items():
        s = paraphrases(b)
        if s in blocks and s != i:
            near.setdefault(i, set()).add(s)
            near.setdefault(s, set()).add(i)
    out = {}
    for start in near:
        if start not in out:
            members = sorted(reach([start], lambda i: near[i]))   # (ids sort by creation)
            out.update((i, members) for i in members)
    return out


def entry_ids(data: dict) -> list[str]:
    """The entries: the top-level blocks, marked `entry`."""
    return [b["id"] for b in data["blocks"] if b.get("entry")]


def sorted_entries(data: dict) -> list[dict]:
    return sorted((b for b in data["blocks"] if b.get("entry")), key=lambda b: b.get("created", ""))


# --- a picture is never held: it's a pericope of its own, quoted where it's shown (fw_store's pictures_apart) ---

def pictures_held(blocks: dict) -> list:
    """(holder, picture) for every picture a block holds as a child."""
    return [(i, k) for i, b in blocks.items() for k in children(unwrap(b)) if image_of(unwrap(blocks.get(k)))]


def picture_quote_id(picture: str, holder: str, taken=frozenset()) -> str:
    """The id of the quote taking `picture`'s place in `holder`: the picture's time and four hex digits from the two
    ids (deterministic, so two machines make the same block)."""
    n = 0
    while (qid := picture[:16] + hashlib.sha1(f"picture {picture} in {holder} {n}".encode()).hexdigest()[:4]) in taken:
        n += 1
    return qid
