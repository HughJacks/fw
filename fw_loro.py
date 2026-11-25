"""fw_loro — the store on disk as a Loro document (a CRDT), so copies on
several machines merge by themselves.

The rest of fw keeps working on the store as plain data ({schemaVersion,
blocks: [Block]}, masks per block, as on disk). This module turns that into
the document and back, and nothing else: `to_data(doc)` reads it, and
`write(doc, data)` makes the document say `data` with the smallest edits it
can (a text edited as a text, children moved rather than removed and added),
so two machines' edits interleave instead of one overwriting the other.

Layout of the document (one root map, "blocks", id -> block map):

    block map    every scalar field as a value (title, entry, created,
                 updated, words, links; paraphrases, before v18, only
                 read), "at" (the order it was added in), and
    "case"       which content it has: "text" | "paraphrase" | "blocks" | "kind" | "value"
    "text"       LoroText              content: a string, or a paraphrase's words
    "paraphrase" the original's id     content: {"paraphrase": id, "text": "…"}
    "children"   LoroMovableList       content: [ids] (a kind's description too)
    "kind"       the kind's name       content: {"kind": name, "blocks": [...]}
    "value"      the content as is     content: a quote or a picture
    "kinds"      LoroMap kind -> [bool, place]   each answer merges on its own
    "visits"     LoroMap               "recent": minute -> flags (a union),
                                       "total": LoroCounter, "first": value

Spans (a link's `at`, a quote's masks: [start, end] in a block's text) are
kept as [start, end, start cursor, end cursor]: Loro cursors on the span's
first and last character, so an edit merged from another machine moves them
with their text (the numbers are what they were when written, used only when
there's no cursor). The start is its first character; the end is its last
character, one past it while it's there, where it was once it's deleted.
`to_data` gives plain [start, end] back, resolved; `write` keeps the cursors
while they still resolve to what the data says, and makes new ones when they
don't (fw moved the span itself, or there were none).

Root map "store" holds schemaVersion (and any other top-level field); root
map "peers" names each machine's peer id (who made a change: attribution
later, without another migration).

A merge can leave what no single machine would make (a block listed by two
containers after moves on both sides, one nobody reaches); the store tidies
that after every merge (fw_store.merge_file), the same way on every machine.
"""

from __future__ import annotations

import loro

FIELDS = ("title", "entry", "created", "updated", "words", "links", "paraphrases")  # values (links' spans as cursors; paraphrases: a mark before v18, read for the migration, then gone)
USES = {"text": ("text",), "paraphrase": ("text", "paraphrase"), "blocks": ("children",), "kind": ("kind", "children"),
        "value": ("value",)}  # what each case keeps in the block's map (a text made a paraphrase keeps its LoroText: its cursors)
VISITS_KEPT = 10


# --- reading ---------------------------------------------------------------------

def plain(span) -> list:
    """A span as written, without its cursors."""
    return list(span[:2])


def content_of(m: dict, at=plain):
    """A block's content from its map (as get_deep_value gives it); its masks'
    spans through `at` (resolved, in to_data)."""
    case = m.get("case")
    if case == "text":
        return m.get("text", "")
    if case == "paraphrase":
        return {"paraphrase": m.get("paraphrase", ""), "text": m.get("text", "")}
    if case == "blocks":
        return list(m.get("children", []))
    if case == "kind":
        return {"kind": m.get("kind", ""), "blocks": list(m.get("children", []))}
    return masked(m.get("value"), at)


def masked(c, at):
    """A quote's content with every span of its mask and inner masks through `at`."""
    if not isinstance(c, dict) or not ("mask" in c or "inner" in c):
        return c
    per = lambda mask: {b: [at(s) for s in spans] for b, spans in mask.items()} if isinstance(mask, dict) else mask
    c = dict(c)
    if "mask" in c:
        c["mask"] = per(c["mask"])
    if isinstance(c.get("inner"), dict):
        c["inner"] = {q: per(m) for q, m in c["inner"].items()}
    return c


def visits_of(v: dict | None) -> dict | None:
    if not v or not v.get("recent"):
        return None
    recent = sorted((int(k), f) for k, f in v["recent"].items())[-VISITS_KEPT:]
    first = v.get("first")
    return {"total": max(int(v.get("total") or 0), len(recent)),
            "first": min(first, recent[0][0]) if first is not None else recent[0][0],
            "recent": [[m, f] for m, f in recent]}


def block_of(i: str, m: dict, at=plain) -> dict:
    """A block as data, from its map (spans through `at`)."""
    b = {"id": i, **{k: m[k] for k in FIELDS if k in m and m[k] is not None}, "content": content_of(m, at)}
    if b.get("links"):
        b["links"] = [{**l, "at": at(l["at"])} for l in b["links"]]
    if not b.get("entry"):
        b.pop("entry", None)  # true or absent
    b.setdefault("title", None)
    if m.get("kinds"):  # each answer [yes?, its place]: the order they were given in (a bare bool: written before places)
        answer = lambda a: a if isinstance(a, list) else [a, 0]
        b["kinds"] = {k: bool(answer(a)[0]) for k, a in sorted(m["kinds"].items(), key=lambda x: (answer(x[1])[1], x[0]))}
    v = visits_of(m.get("visits"))
    if v:
        b["visits"] = v
    return b


def to_data(doc: loro.LoroDoc) -> dict:
    """The store as plain data, the blocks in the order they were added (`at`; ids break ties)."""
    v = doc.get_deep_value()
    store = dict(v.get("store") or {})
    blocks = v.get("blocks") or {}
    order = sorted(blocks, key=lambda i: (blocks[i].get("at", 0), i))  # the order they were added in
    at = lambda span: resolve(doc, span)
    return {**store, "blocks": [block_of(i, blocks[i], at) for i in order]}


def resolve(doc: loro.LoroDoc, span) -> list:
    """A span where its cursors are now (its numbers if it has none)."""
    if len(span) < 4 or span[2] is None:
        return plain(span)
    try:
        start = doc.get_cursor_pos(loro.Cursor.decode(span[2])).current.pos
        if span[3] is None:
            return [start, start]
        end = doc.get_cursor_pos(loro.Cursor.decode(span[3])).current
    except Exception:  # (a cursor into a text that's gone)
        return plain(span)
    return [start, max(start, end.pos + (end.side == loro.Side.Right))]


# --- writing ---------------------------------------------------------------------

def child(m: loro.LoroMap, key: str, kind):
    return m.get_or_create_container(key, kind())


def same_list(lst: loro.LoroMovableList, want: list) -> None:
    """Make `lst` hold `want`, in order: what's gone deleted, what's new
    inserted, the rest moved (so a move on another machine merges as one)."""
    have = lst.get_deep_value()
    for n in reversed(range(len(have))):
        if have[n] not in want or have[n] in have[:n]:
            lst.delete(n, 1)
            have.pop(n)
    for n, x in enumerate(want):
        if n < len(have) and have[n] == x:
            continue
        if x in have:
            lst.mov(have.index(x), n)
            have.insert(n, have.pop(have.index(x)))
        else:
            lst.insert(n, x)
            have.insert(n, x)


def set_value(m: loro.LoroMap, key: str, value) -> None:
    if value is None:
        if m.get(key) is not None:
            m.delete(key)
    elif m.get_deep_value().get(key) != value:
        m.insert(key, value)


def write_content(m: loro.LoroMap, content) -> None:
    case = ("text" if isinstance(content, str) else "blocks" if isinstance(content, list)
            else "kind" if isinstance(content, dict) and "kind" in content
            else "paraphrase" if isinstance(content, dict) and "paraphrase" in content else "value")
    if m.get_deep_value().get("case") != case:
        for k in ("text", "children", "kind", "value", "paraphrase"):
            if k not in USES[case] and m.get(k) is not None:
                m.delete(k)
        m.insert("case", case)
    if case in ("text", "paraphrase"):
        text = content if case == "text" else content.get("text", "")
        t = child(m, "text", loro.LoroText)
        if t.to_string() != text:
            t.update(text)
        if case == "paraphrase":
            set_value(m, "paraphrase", content["paraphrase"])
    elif case == "blocks":
        same_list(child(m, "children", loro.LoroMovableList), content)
    elif case == "kind":
        set_value(m, "kind", content["kind"])
        same_list(child(m, "children", loro.LoroMovableList), list(content.get("blocks", [])))
    # a quote's or a picture's value: write_spans


def write_kinds(m: loro.LoroMap, answers: dict) -> None:
    if not answers and m.get("kinds") is None:
        return
    k = child(m, "kinds", loro.LoroMap)
    have = k.get_deep_value()
    for kid in have:
        if kid not in answers:
            k.delete(kid)
    for n, (kid, a) in enumerate(answers.items()):
        if have.get(kid) != [a, n]:
            k.insert(kid, [a, n])


def write_visits(m: loro.LoroMap, v: dict | None) -> None:
    """Visits merge as a union: each machine adds the minutes it saw (and only
    takes away the ones it had itself: older than the last VISITS_KEPT); the
    total is a counter, so both sides' counts add up."""
    if not v and m.get("visits") is None:
        return
    vm = child(m, "visits", loro.LoroMap)
    recent = child(vm, "recent", loro.LoroMap)
    want = {str(minute): flags for minute, flags in (v or {}).get("recent", [])}
    for key in recent.keys():
        if key not in want:
            recent.delete(key)
    have = recent.get_deep_value()
    for key, flags in want.items():
        if have.get(key) != flags:
            recent.insert(key, flags)
    total = child(vm, "total", loro.LoroCounter)
    goal = (v or {}).get("total", 0)
    if goal != total.value:
        (total.increment if goal > total.value else total.decrement)(abs(goal - total.value))
    set_value(vm, "first", (v or {}).get("first"))


def write_block(m: loro.LoroMap, b: dict) -> None:
    """All of a block but its spans (write_spans, once every text is written)."""
    for k in FIELDS:
        if k != "links":
            set_value(m, k, b.get(k))
    write_content(m, b["content"])
    write_kinds(m, b.get("kinds") or {})
    write_visits(m, b.get("visits"))


class Spans:
    """Spans into the document's texts: `encode` gives one cursors, `bare`
    says whether stored ones could have cursors and haven't."""

    def __init__(self, doc: loro.LoroDoc, blocks: loro.LoroMap):
        self.doc, self.blocks, self.texts = doc, blocks, {}

    def text(self, bid: str):
        """The LoroText of block `bid`, or None (no such block, or not text)."""
        if bid not in self.texts:
            t = None
            if self.blocks.get(bid) is not None:
                m = child(self.blocks, bid, loro.LoroMap)
                if m.get_deep_value().get("case") in ("text", "paraphrase"):
                    t = child(m, "text", loro.LoroText)
            self.texts[bid] = t
        return self.texts[bid]

    def encode(self, bid: str, span) -> list:
        s, e = span[0], span[1]
        t = self.text(bid)
        if t is None or not 0 <= s <= e <= t.len_unicode:
            return [s, e]  # (not a text's span: a quote inside a mask, [0, 1])
        cs = t.get_cursor(s, loro.Side.Left)
        ce = t.get_cursor(e - 1, loro.Side.Right) if e > s else None
        return [s, e, cs.encode() if cs else None, ce.encode() if ce else None]

    def resolve(self, span) -> list:
        return resolve(self.doc, span)

    def bare(self, bid: str, stored) -> bool:
        """Some of the spans `stored` (in the document) have no cursors and could (written before them)."""
        return any(len(s) < 4 and len(self.encode(bid, s)) == 4 for s in stored)


def write_spans(m: loro.LoroMap, b: dict, sp: Spans) -> None:
    """A block's links, and a quote's or picture's value (its masks), as cursors
    into the texts they point at; left as they are while they still resolve to the data."""
    have = m.get_deep_value()
    links = b.get("links")
    if links is None:
        if have.get("links") is not None:
            m.delete("links")
    else:
        stored = have.get("links") or []
        same = (len(stored) == len(links)
                and all({**s, "at": None} == {**l, "at": None} for s, l in zip(stored, links))
                and [sp.resolve(s["at"]) for s in stored] == [plain(l["at"]) for l in links]
                and not sp.bare(b["id"], [s["at"] for s in stored]))
        if not same:
            m.insert("links", [{**l, "at": sp.encode(b["id"], l["at"])} for l in links])
    c = b["content"]
    if isinstance(c, str) or isinstance(c, list) or isinstance(c, dict) and ("kind" in c or "paraphrase" in c):
        return
    stored = have.get("value")
    if masked(stored, sp.resolve) != c or any(sp.bare(bid, spans) for bid, spans in mask_spans(stored)):
        m.insert("value", masked_encoded(c, sp))


def mask_spans(c) -> list:
    """(block id, its spans) for every mask in a quote's content (`mask`, then each of `inner`)."""
    if not isinstance(c, dict):
        return []
    masks = ([c["mask"]] if isinstance(c.get("mask"), dict) else []) + \
            [m for m in (c.get("inner") or {}).values() if isinstance(m, dict)]
    return [(bid, spans) for mask in masks for bid, spans in mask.items()]


def masked_encoded(c, sp: Spans):
    """A quote's content with its masks' spans as cursors (anything else as is)."""
    if not isinstance(c, dict) or not ("mask" in c or "inner" in c):
        return c
    per = lambda mask: {b: [sp.encode(b, s) for s in spans] for b, spans in mask.items()} if isinstance(mask, dict) else mask
    c = dict(c)
    if "mask" in c:
        c["mask"] = per(c["mask"])
    if isinstance(c.get("inner"), dict):
        c["inner"] = {q: per(m) for q, m in c["inner"].items()}
    return c


def same_block(a: dict | None, b: dict) -> bool:
    """Block `b` just as `a` says it (its tags' order too: they're kept in the order given)."""
    return a == b and list((a.get("kinds") or {}).items()) == list((b.get("kinds") or {}).items())


def has_spans(b: dict) -> bool:
    """Block `b` holds spans into texts (links, or a quote's or picture's masks), which can move with another's text."""
    c = b["content"]
    return bool(b.get("links")) or isinstance(c, dict) and not ("kind" in c or "paraphrase" in c)


def write(doc: loro.LoroDoc, data: dict, old: dict | None = None) -> None:
    """Make `doc` say `data` (the store as on disk), with the fewest edits; commits. With `old`, what `doc` says now
    (to_data), only the blocks that differ from it are written (and every block's spans, which follow others' texts):
    a save writes what changed, not the whole store."""
    blocks = doc.get_map("blocks")
    want = {b["id"]: b for b in data["blocks"]}
    was = {b["id"]: b for b in old["blocks"]} if old is not None else {}
    for i in blocks.keys():
        if i not in want:
            blocks.delete(i)
    have = set(blocks.keys())
    new = [i for i in want if i not in have]
    at = max((v.get("at", 0) for v in blocks.get_deep_value().values()), default=0) if new else 0
    changed = [i for i in want if old is None or not same_block(was.get(i), want[i])]
    for i in changed:
        m = child(blocks, i, loro.LoroMap)
        if i not in have:
            at += 1
            m.insert("at", at)
        write_block(m, want[i])
    sp = Spans(doc, blocks)  # then the spans, every text now as the data has it
    for i in dict.fromkeys(changed + [i for i, b in want.items() if has_spans(b)]):
        write_spans(child(blocks, i, loro.LoroMap), want[i], sp)
    store = doc.get_map("store")
    for k in store.keys():
        if k not in data:
            store.delete(k)
    for k, v in data.items():
        if k != "blocks":
            set_value(store, k, v)
    doc.commit()


# --- the file and the machine ---------------------------------------------------------

def load(raw: bytes | None, peer: int) -> loro.LoroDoc:
    doc = loro.LoroDoc()
    if raw:
        doc.import_(raw)
    doc.peer_id = peer
    return doc


def snapshot(doc: loro.LoroDoc) -> bytes:
    return doc.export(loro.ExportMode.Snapshot())


def name_peer(doc: loro.LoroDoc, name: str) -> None:
    """Say which machine this peer id is (once)."""
    peers = doc.get_map("peers")
    if peers.get_deep_value().get(str(doc.peer_id)) != name:
        peers.insert(str(doc.peer_id), name)
        doc.commit()


def version(doc: loro.LoroDoc) -> str:
    """Where `doc` is now, as a string a page keeps and sends back with its edits (its frontiers, hex)."""
    return doc.oplog_frontiers.encode().hex()


def fork_at(doc: loro.LoroDoc, at: str) -> loro.LoroDoc:
    """A copy of `doc` as it was at version `at` (version), a peer of its own: edits made in it merge back (merge_fork)."""
    return doc.fork_at(loro.Frontiers.decode(bytes.fromhex(at)))


def merge_fork(doc: loro.LoroDoc, fork: loro.LoroDoc, at: str) -> None:
    """What was written in `fork` since version `at` merged into `doc`, with whatever `doc` has had since."""
    doc.import_(fork.export(loro.ExportMode.Updates(doc.frontiers_to_vv(loro.Frontiers.decode(bytes.fromhex(at))))))


def merge(doc: loro.LoroDoc, raw: bytes) -> None:
    """Another copy's changes into `doc` (any order, any number of times: the same result)."""
    doc.import_(raw)
