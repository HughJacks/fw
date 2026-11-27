# the draft (fw's text format for a block: {{block id}} marker lines, quotes as {{quote id}} lines, nesting named on
# the markers) and commit, which writes a draft into the store: blocks split, joined, nested, emptied, taken out
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("draft")
A, T, QE = "20261001T100000-aaaa", "20261002T100000-bbbb", "20261003T100000-cccc"
C1, C2 = "20261001T100000-c001", "20261001T100000-c002"
q, b1, b2 = S.quote_line(A), S.block_line(C1), S.block_line(C2)

# --- the format, pure
same("trailing blank lines trimmed", S.draft_items(f"{b1}\nabc\n\n"), [("text", C1, "abc")])
same("blank lines around a quote are spacing", S.draft_items(f"{b1}\na\n\n{q}\n\n"), [("text", C1, "a"), ("quote", A, None)])
same("leading blank lines and whitespace-only lines", S.draft_items(f"{b1}\n\n  \nabc\n \n"), [("text", C1, "abc")])
same("paragraph breaks inside a block kept", S.draft_items(f"{b1}\na\n\nb"), [("text", C1, "a\n\nb")])
same("all blank: nothing", S.draft_items(f"{b1}\n\n\n \n"), [])
same("blank edges trimmed per block", S.draft_items(f"{b1}\none\n\n{b2}\n\ntwo\n"), [("text", C1, "one"), ("text", C2, "two")])
items = S.draft_items(f"x\n{q}\ny")
same("text without markers: new blocks with fresh ids", [(i[0], i[2] if i[0] == "text" else i[1]) for i in items], [("text", "x"), ("quote", A), ("text", "y")])
check("  the two ids differ", items[0][1] != items[2][1])
lines, bids = S.parse_draft(f"{b1}\none\n{b1}\ntwo")
same("a repeated marker is a new block", (lines, bids[0] == C1, bids[1] != C1), (["one", "two"], True, True))
same("format_draft inverts parse_draft", S.format_draft(*S.parse_draft(f"{b1}\none\n{q}\n{b2}\ntwo")), f"{b1}\none\n{q}\n{b2}\ntwo")
same("nesting: a marker names the containers it's in", S.draft_items(f"{S.block_line(C2, (C1,))}\ninside"), [("blocks", C1, [("text", C2, "inside")])])

# --- words: a word is something besides punctuation; an inline expression ($…$) one word
same("words: an inline expression counts one, its code none", S.word_count("the train $wordCount(@20261001T100000-aaaa) + 1$ arrives"), 4)
same("  a lone $, or \\$, is just part of its word", S.word_count("a lone 300$ stays, 30\\$ each"), 6)
same("  a + or a ? alone isn't one", S.word_count("31 + ?"), 1)
same("  nor a dash, a bullet, dots or a typographic mark; letters, digits, accents are", S.word_count("- café — naïve ... “x” 1974 •"), 4)

# --- commit
SELF, X, Y = "20261021T230000-0000", "20261021T230000-c001", "20261021T230000-c002"
def fresh(*kids):
    F.store(blk(SELF, [k[0] for k in kids], "mine", entry=True), *[blk(i, t) for i, t in kids])
def put(draft): S.commit(SELF, draft, [])
def ids(): return S.children(F.blocks()[SELF])
fresh((X, "hello world"))
put(f"{S.block_line(X)}\nhello \n{{{{block}}}}\nworld")
same("a block split in two: the first keeps its id", (F.kids(SELF), ids()[0]), (["hello ", "world"], X))
put(f"{S.block_line(X)}\nhelloworld")
same("  joined back: the other erased from the store", (F.kids(SELF), len(F.blocks())), (["helloworld"], 2))
fresh((X, "one two"), (Y, "three"))
same("an entry's words count all its blocks", F.blocks()[SELF]["words"], 3)
put(f"{S.block_line(X)}\none\n{{{{block}}}}\n\n{{{{block}}}}\n   \n{S.block_line(Y)}\n")
same("empty blocks (blank, spaces, emptied) aren't kept", (F.kids(SELF), len(F.blocks())), (["one"], 2))
F.store(blk(SELF, "just text", entry=True))
S.commit(SELF, "changed text", [])
same("a block of plain text stays plain while it's one run", F.content(SELF), "changed text")
S.commit(SELF, "one\n{{block}}\ntwo", [])
same("  and becomes a list of children once it has two", F.kids(SELF), ["one", "two"])
F.store(blk(SELF, "see $1 + 2 + 3$ go", entry=True))
same("the stored count: an inline expression one word", F.blocks()[SELF]["words"], 3)

# nesting: a block inside a block (a container), to any depth
H1, E, E1, E2 = "20261001T100000-e000", "20261001T100000-e001", "20261001T100000-e002", "20261001T100000-e003"
fresh((H1, "abcdef"), (X, "end"))
put(f"{S.block_line(Y, (H1,))}\nabc\n{S.block_line(E, (H1,))}\ndef\n{S.block_line(X)}\nend")
same("a block split a level down: it holds its text either side", F.kids(SELF), [["abc", "def"], "end"])
check("  keeping its id, now a container", ids()[0] == H1)
put(f"{S.block_line(Y, (H1,))}\nabc\n{S.block_line(E2, (E, H1))}\ndef\n{S.block_line(E1, (E, H1))}\ndeep\n{S.block_line(X)}\nend")
same("  a level deeper", F.kids(SELF), [["abc", ["def", "deep"]], "end"])
before = S.block_draft(F.blocks(), SELF)
S.commit(SELF, before, [])
same("  saved unchanged: as it was", S.block_draft(F.blocks(), SELF), before)
put(f"{S.block_line(Y, (H1,))}\nabcdef\n{S.block_line(X)}\nend")
same("joined back to one run: plain text again, the container's id kept", (F.kids(SELF), ids()[0]), (["abcdef", "end"], H1))
fresh((H1, "top"), (X, "x"))
F.edit(lambda d, b: (b[X].update(content=[E1, E2]), S.add_block(d, b, E1, "x1"), S.add_block(d, b, E2, "y1")))
d = S.block_draft(F.blocks(), SELF)
put(d.replace("x1", "x1, edited"))
same("a container's text edited: still nested", F.kids(SELF), ["top", ["x1, edited", "y1"]])

# a block taken out by an edit: a quote of it elsewhere keeps the last of what it showed, as text
NOTES, N1, N2, ME, QP = ("20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002",
                         "20261002T100000-b000", "20261002T100000-b001")
F.store(blk(NOTES, [N1, N2], "notes", entry=True), blk(N1, "first idea"), blk(N2, "second idea"),
        blk(ME, [QP], "mine", entry=True), blk(QP, {"quote": N2}))
_, _, record, _ = S.commit(NOTES, f"{S.block_line(N1)}\nfirst idea", [])
same("taking a quoted block out of its entry: its quote elsewhere keeps its text", (F.kids(NOTES), F.kids(ME)), (["first idea"], ["second idea"]))
S.restore(record)
S.commit(NOTES, f"{S.block_line(N1)}\nfirst idea\n{S.block_line(N2)}\nsecond idea", [])
same("  its record (and the draft again) put both back", (F.kids(NOTES), F.kids(ME)), (["first idea", "second idea"], [("quote", N2)]))

# a save made on a block changed since: refused (with no version to merge from)
base = S.content_hash(F.blocks(), NOTES)
S.commit(NOTES, f"{S.block_line(N1)}\nchanged elsewhere\n{S.block_line(N2)}\nsecond idea", [])
check("a save on an old base: refused, the other text kept", F.refused(S.commit, NOTES, "mine", [], base=base)
      and S.own_text(F.blocks(), NOTES).startswith("changed elsewhere"))
F.report()
