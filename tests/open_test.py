import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, QUIT as Q, UNDO as Z, UP, DOWN, LEFT, ESC, MENU
S = F.use_store("t/open.json", clean=True)
SRC, CS = "20261001T100000-5a00", "20261001T100000-5a01"
HOST, CH, QH = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
MASKED, QM = "20261001T100000-c000", "20261001T100000-c001"
A, CA, QA = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
B, CB, QB = "20261001T100000-bb00", "20261001T100000-bb01", "20261001T100000-bb02"
src = [blk(SRC, [CS], "src"), blk(CS, "alpha line\nbeta line")]
draft = S.block_draft({b["id"]: b for b in src}, SRC); beta = draft.index("beta")
F.write_store(src + [
    blk(HOST, [CH, QH], "host"), blk(CH, "host text"), blk(QH, {"quote": SRC}),
    blk(MASKED, [QM], "masked"), blk(QM, {"quote": SRC, "mask": [beta, beta + len("beta line")]}),
    blk(A, [CA, QA], "cyc a"), blk(CA, "cycle a"), blk(QA, {"quote": B}),       # a quotes b,
    blk(B, [CB, QB], "cyc b"), blk(CB, "cycle b"), blk(QB, {"quote": A}),       # which quotes a
], [SRC, HOST, MASKED, A, B])
def text(i): return S.own_text(S.index(S.load_data()), i)
def bar(t): return t.row(t.scr.lines - 1)
OPEN = (MENU, "open", "\r")

f = F.fw("host")   # opens at the end, on the empty line below the quote
f.key("Y"); f.settle(); f.key(UP, MENU)
check("Open it is in the menu on a selected quote", "Open it" in f.text(), f.text())
f.key("open", "\r")
check("Open it steps into the quote's source", "alpha line" in f.text() and "host text" not in f.text(), f.text())
check("  the bar shows the trail and ^Q back", "host ›" in bar(f) and "^Q back" in bar(f), bar(f))
f.key("X"); f.settle()
check("  it opens at the start, and edits the source", text(SRC).startswith("Xalpha"), text(SRC))
f.key(Q)
check("^Q steps back to where Open it was", "host text" in f.text() and "Xalpha line" in f.text() and "host ›" not in bar(f), f.text())
f.key(Z); f.settle()
check("  with its undo intact: ^Z undoes what was typed before", "Y" not in text(HOST), text(HOST))
check("  and stepping in was no undo step: the source keeps its edit", text(SRC).startswith("Xalpha"), text(SRC))
f.key(Q)
check("^Q again goes home", "open ›" in f.text(), f.text())
f.key(ESC); check("  and Esc quits", f.done())

i = F.fw("host")
i.key(UP, UP, LEFT, LEFT)   # into the quote from below (its last row, column 0), then 2 back: "Xalpha lin|e"
i.key(MENU)
check("inside a quote, not selecting it: the menu still offers Open it", "Open it" in i.text(), i.text())
i.key("open", "\r", "W"); i.settle()
check("  it opens the quote it's in, at the cursor", "Xalpha linWe" in text(SRC) and "host ›" in bar(i), text(SRC))
i.key(Q)
check("  and ^Q comes back inside the quote, which shows the edit", "Xalpha linWe" in i.text() and "host ›" not in bar(i), i.text())
i.key(Q, ESC); i.done()

g = F.fw("masked")
g.key(UP, *OPEN)
check("a masked quote opens its whole source", "alpha lin" in g.text() and "beta line" in g.text(), g.text())
g.key("Z"); g.settle()
check("  at its first shown part", "Zbeta line" in text(SRC), text(SRC))
g.key(Z); g.settle()
check("^Z after Open it undoes what was typed there first", text(SRC).startswith("Xalpha") and "Zbeta" not in text(SRC) and "masked ›" in bar(g), text(SRC))
g.key(Z)
check("  then, with nothing left, steps back", "masked ›" not in bar(g) and "^Q back" not in bar(g), bar(g))
g.key(Z); g.settle()
check("  and with no trail, ^Z doesn't leave the entry", "open ›" not in g.text(), g.text())
g.key(Q, ESC); g.done()

h = F.fw("cyc a", rows=24)   # (a quote's blocks each in a box: room for it all)
h.key(UP, *OPEN)
check("a cycle: a → b", "cycle b" in h.text() and "cyc a ›" in bar(h), bar(h))
h.key(DOWN, *OPEN)   # down onto the quote of a
check("  → a again, on the trail twice", "cyc a ›  cyc b ›" in bar(h), bar(h))
h.key("!"); h.settle(); h.key(Q, Q)
check("  stepping back twice: the first a shows the edit", "cyc a ›" not in bar(h) and "!cycle a" in h.text(), h.text())
h.key(Q, ESC); h.done()
check("  and the store has it", text(A).startswith("!cycle a"), text(A))
check("no drafts left behind", not [x for x in os.listdir(F.DEV) if x.startswith(".fw-")], [x for x in os.listdir(F.DEV) if x.startswith(".fw-")])
F.report("OPEN")
