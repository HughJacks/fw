import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, LEFT, RIGHT, HOME, END, ESC, ENTER, QUIT as Q, UNDO as Z, REDO as Y, MENU
S = F.use_store("t/nest.json", clean=True)
HOST, CH, C2 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
OTHER, CO, QO = "20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002"
SENT = "I went to the alley and the lanes were waxed so we bowled late."
def fresh():
    F.write_store([blk(HOST, [CH, C2], "host"), blk(CH, SENT), blk(C2, "next block"),
                   blk(OTHER, [CO, QO], "other"), blk(CO, "other text"), blk(QO, {"quote": HOST})], [HOST, OTHER])
def B(): return S.index(S.load_data())
def kids(i): return [B()[k]["content"] for k in S.children(B()[i])]
def bar(t): return t.row(t.scr.lines - 1)
SEL = "\x1b[1;2C"   # shift+right
CTRL_T, CTRL_ST = "\x14", "\x1b[116;6u"
def select_waxed(t):  # "the lanes were waxed", in block 1
    t.key(UP, UP, HOME, *[RIGHT] * 24, *[SEL] * 20)

fresh(); t = F.fw("host", rows=24)
select_waxed(t)
t.key(MENU)
check("with a selection the menu offers Turn into a quote, for the selection", "nested here" in t.text(), t.text())
t.key(ESC, CTRL_T); t.settle()
check("ctrl+t on a selection: the block holds its text before, the quote, its text after",
      kids(CH)[0] == "I went to the alley and" and S.quoted(B()[S.children(B()[CH])[1]]) and kids(CH)[2] == "so we bowled late.", kids(CH))
new = S.quoted(B()[S.children(B()[CH])[1]])[0]
same("  the new entry holds the selection", S.own_text(B(), new), "the lanes were waxed")
check("  it's an entry of its own", new in S.entry_ids(S.load_data()))
check("  the block keeps its id and box, the quote drawn inside it",
      "│┏━" in t.text() and "││  the lanes were waxed" in t.text() and t.text().count("1 ┌") == 1, t.text())
check("  and its number: block 2 is still the next block", "2 ┌" in t.text() and "next block" in t.text(), t.text())
same("words count the quoted text once", B()[HOST]["words"], len((SENT + " next block").split()))

t.key(DOWN, END, "!"); t.settle()   # from the quote (where the cursor lands) to the text after it
check("typing in the text after it, inside the container, keeps it nested", kids(CH)[2] == "so we bowled late.!", kids(CH))
t.key(ENTER, "more"); t.settle()
check("  Enter there makes a new block in the container too", kids(CH)[3:] == ["more"] and len(S.children(B()[HOST])) == 2, (kids(CH), S.children(B()[HOST])))
t.key(UP, UP, UP, "X"); t.settle()
check("typing inside the nested quote edits its source", "X" in S.own_text(B(), new), S.own_text(B(), new))
t.key(Q, ESC); t.done()

t = F.fw("host", rows=24)
check("reopened, the container is still one box with the quote inside", t.text().count("1 ┌") == 1 and "│┌─" in t.text(), t.text())
t.key(Q, ESC); t.done()

o = F.fw("other", rows=26)
check("a quote of the entry shows the container's text with its quote inside", "I went to the alley and" in o.text() and "lanes were waxed" in o.text(), o.text())
o.key(Q, ESC); o.done()

fresh(); t = F.fw("host", rows=24)
select_waxed(t)
t.key(CTRL_T); t.settle()
t.key(Z); t.settle()
check("^Z takes it all back: the block's text, no new entry", B()[CH]["content"] == SENT and len(S.entry_ids(S.load_data())) == 2, B()[CH]["content"])
t.key(Y); t.settle()
check("  ^Y does it again", isinstance(B()[CH]["content"], list), B()[CH]["content"])
t.key(UP, HOME, *[SEL] * 6, CTRL_T); t.settle()   # "I went", in the container's first child
check("a selection in a container's child splits it there, not a level deeper",
      [type(c).__name__ for c in kids(CH)] == ["dict", "str", "dict", "str"] and kids(CH)[1] == "to the alley and", kids(CH))
t.key(Q, ESC); t.done()

fresh(); t = F.fw("host", rows=24)
select_waxed(t)
t.key(CTRL_ST)
check("ctrl+shift+t on a selection: nested, then opened", "host ›" in bar(t) and "the lanes were waxed" in t.text(), bar(t))
t.key(Q, Q, ESC); t.done()

fresh(); t = F.fw("host", rows=24)
t.key(UP, UP, HOME, "\x1b[1;2B", "\x1b[1;2B", CTRL_T)
check("two blocks selected whole: a command says it acts on one", "select within one block" in bar(t) and B()[CH]["content"] == SENT, bar(t))
t.key(Q, ESC); t.done()
check("no drafts left behind", not [x for x in os.listdir(F.DEV) if x.startswith(".fw-")], os.listdir(F.DEV))
F.report("NEST")
