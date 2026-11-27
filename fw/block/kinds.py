"""Kinds (tags on screen): what a pericope is. A kind is a top-level block whose content is a Kind; a pericope keeps
the answers given in `kinds`, {kind id: True | False}. A model's guesses (kind-guesses.json) are never stored:
`guessed` keeps those that count, and they meet the answers in merge_kinds, where the answers win."""

from __future__ import annotations

from fw.block.case import kind_of, unwrap

GUESS_AT = 0.9   # a guess counts, and is applied, from this p(yes) up
MAYBE_AT = 0.5   # from this up to GUESS_AT it's a maybe, to review
PROPOSE_AT = 5   # a proposed kind is offered while this many of its pericopes are uncovered
NOT = "not "     # in the header's kinds: "poem, not letter"


def kinds_of(b: dict | None) -> dict:
    """The answers given for `b` (unwraps): {kind id: bool}."""
    b = unwrap(b)
    return dict(b.get("kinds") or {}) if b else {}


def merge_kinds(answers: dict, guesses: dict | None = None) -> dict:
    """What a block is, all told: guesses ({kind id: p}) at GUESS_AT or over a yes, under the answers."""
    return {**{k: True for k, p in (guesses or {}).items() if p >= GUESS_AT}, **answers}


def guessed(data, blocks: dict, at: float = GUESS_AT) -> dict:
    """The guesses that count, {block id: {kind id: p}}, out of kind-guesses.json (`data`: {guesses: {kind id:
    {block id: [p, kind's updated, block's updated]}}}): kinds and pericopes still here, unanswered, current (both
    `updated` as the guess has them), p at `at` or over. Anything malformed counts for nothing."""
    per_kind = data.get("guesses") if isinstance(data, dict) else None
    out = {}
    for kid in sorted(per_kind) if isinstance(per_kind, dict) else []:
        k, said = unwrap(blocks.get(kid)), per_kind[kid]
        if kind_of(k) is None or not isinstance(said, dict):
            continue
        for bid, g in said.items():
            b = unwrap(blocks.get(bid))
            match g:
                case [int() | float() as p, str() as ku, str() as bu] if (
                        b is not None and b.get("entry") and p >= at and kid not in kinds_of(b)
                        and ku == k.get("updated") and bu == b.get("updated")):
                    out.setdefault(bid, {})[kid] = p
    return out


def learned(data) -> set:
    """The kinds a model learned from the answers (kind-guesses.json's `sources`, source "learned")."""
    sources = data.get("sources") if isinstance(data, dict) else None
    return ({k for k, v in sources.items() if isinstance(v, dict) and v.get("source") == "learned"}
            if isinstance(sources, dict) else set())


def is_applied(blocks: dict, bid: str, kid: str, learned_kinds) -> bool:
    """A guess that counts is applied, not asked, whatever model or block: only those under GUESS_AT are maybes."""
    return True


def maybes(data, blocks: dict, kid: str) -> list:
    """Kind `kid`'s maybes to review: pericopes guessed one from MAYBE_AT up to GUESS_AT, unanswered and current,
    [(block id, p)], likeliest first (then oldest)."""
    entry = lambda i: bool((unwrap(blocks.get(i)) or {}).get("entry"))
    found = [(i, g[kid]) for i, g in guessed(data, blocks, MAYBE_AT).items()
             if kid in g and i != kid and g[kid] < GUESS_AT and entry(i)]
    return sorted(found, key=lambda x: (-x[1], x[0]))


def kind_cover(blocks: dict, data) -> set:
    """The pericopes some kind covers: a yes said, or a guess applied."""
    out = {i for i, b in blocks.items() if True in kinds_of(b).values()}
    auto = learned(data)
    return out | {i for i, g in guessed(data, blocks).items() if any(is_applied(blocks, i, k, auto) for k in g)}


def open_proposals(data, blocks: dict, dismissed, covered: set) -> list:
    """The kinds a model proposes (kind-proposals.json, {proposals: [{id, name, description, members, typical}]})
    still worth offering, members now only pericopes still here that no kind covers (`covered`). Dropped: fewer than
    PROPOSE_AT left, a kind of that name, or dismissed (kind-dismissed.json, {dismissed: [{name, members}]}: the
    same name, or half the members or more in common). Anything malformed counts for nothing."""
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
        here = [m for m in members if isinstance(m, str) and (unwrap(blocks.get(m)) or {}).get("entry") and m not in covered]
        if len(here) < PROPOSE_AT or kind_named(blocks, name) is not None or any(alike(d, name, members) for d in said):
            continue
        out.append({**p, "name": tidy_name(name), "members": here,
                    "typical": [t for t in p.get("typical") or [] if isinstance(t, str) and unwrap(blocks.get(t)) is not None],
                    "description": str(p.get("description") or "")})
    return out


def kind_ids(blocks: dict) -> list:
    """The kinds, oldest first; store or library."""
    return sorted(i for i, b in blocks.items() if kind_of(unwrap(b)) is not None)


def tidy_name(name: str) -> str:
    """A kind's name as kept: its spacing tidied."""
    return " ".join(name.split())


def same_name(a: str, b: str) -> bool:
    """The same kind's name, case and spacing aside."""
    return tidy_name(a).casefold() == tidy_name(b).casefold()


def kind_named(blocks: dict, name: str) -> str | None:
    """The kind called `name`, case and spacing aside."""
    return next((i for i in kind_ids(blocks) if same_name(kind_of(unwrap(blocks[i])), name)), None)


def of_kind(blocks: dict, kid: str, guesses: dict | None = None) -> list:
    """The blocks that are kind `kid` by merge_kinds (`guesses` as `guessed` gives them), oldest first."""
    guesses = guesses or {}
    return sorted(i for i, b in blocks.items() if merge_kinds(kinds_of(b), guesses.get(i)).get(kid) is True)


def parse_kinds(text: str) -> list:
    """The header's kinds field -> [(name, yes)], each name once (the last word on it wins)."""
    out = {}
    for part in text.split(","):
        name = " ".join(part.split())
        yes = not name.casefold().startswith(NOT)
        name = name if yes else " ".join(name[len(NOT):].split())
        if name:
            out = {k: v for k, v in out.items() if not same_name(k, name)} | {name: yes}
    return list(out.items())


def kinds_text(blocks: dict, b: dict | None) -> str:
    """`b`'s answers as the header shows them, "poem, not letter" (kinds gone left out)."""
    name_of = lambda i: kind_of(unwrap(blocks[i])) if i in blocks else None
    return ", ".join(("" if yes else NOT) + name_of(k) for k, yes in kinds_of(b).items() if name_of(k))
