# blocks selected whole inside a quote: Esc, Esc again, Shift+↑/↓, a text selection snapping to blocks, acting on them
import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, END, ESC, BS, QUIT as Q, UNDO as Z
S = F.use_store("t/qblocks.json", clean=True)
ME, Q1, X = "20261021T230000-0000", "20261021T230000-0001", "20261021T230000-0002"
A, QAB, A1, A2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002", "20261001T100000-a003"
B, B1 = "20261001T100000-b000", "20261001T100000-b001"
P, PM = "20261001T100000-c000", "20261021T230000-0003"
SUP, SDOWN, COPY, PASTE = "\x1b[1;2A", "\x1b[1;2B", "\x03", "\x16"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}
def fresh(quote=None):
    F.write_store([blk(A, [QAB, A1, A2], "Alpha"), blk(QAB, {"quote": B}), blk(A1, "alpha one"), blk(A2, "alpha two"),
                   blk(B, [B1], "Beta"), blk(B1, "beta"), blk(P, "plain words", "Plain"),
                   blk(ME, [Q1, X], "mine"), blk(Q1, quote or {"quote": A}), blk(X, "x")], [A, B, P, ME])
    S.cmd_migrate(None)
def B_(): return S.index(S.load_data())
def kids(i):
    b = B_()
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else kids(k) if S.children(b[k]) else b[k]["content"]
            for k in S.children(b[i])]
def bar(t): return t.row(t.scr.lines - 1)
def lit(t, text):  # the faint box around a block of text, lit (bold) where it's selected whole
    y = next(y for y in range(t.scr.lines) if t.inside(y) == text)
    return t.cell(y, 3).bold
def open_mine(quote=None):
    fresh(quote)
    return F.fw("mine", rows=30, env=ENV)

t = open_mine()   # at the end of "x"
t.key(UP, UP)     # the quote selected from below, then into it: the end of "alpha two"
check("into the quote: on its last block", "Alpha" in bar(t) and " 3:" in bar(t), bar(t))
t.key(ESC)
check("Esc selects the block you're in, inside the quote", "block 3" in bar(t), bar(t))
check("  its box lit, not the other blocks'", lit(t, "alpha two") and not lit(t, "alpha one"), t.text())
t.key(SUP)
check("Shift+↑ adds the block above, inside the quote", "blocks 2–3" in bar(t) and lit(t, "alpha one"), bar(t))
t.key(SUP)
check("  and the quote inside it", "blocks 1–3" in bar(t), bar(t))
t.key(ESC)
check("Esc again: the quote around them, selected", "block" not in bar(t) and "Alpha" in bar(t) and "1:1" in bar(t), bar(t))
t.key(Q, ESC); t.done()

t = open_mine()
t.key(UP, UP, SUP)   # a text selection from the end of "alpha two" up into "alpha one"
check("a text selection reaching another block inside a quote: whole blocks", "blocks 2–3" in bar(t), bar(t))
t.key(COPY, ESC, DOWN)   # copied; Esc: the quote selected; Down: on past it, onto x
t.key(END, PASTE); t.settle()
same("  copied, ^V pastes quotes of them in the entry (in x's text: inside it)", kids(ME), [("quote", A), ["x", ("quote", A1), ("quote", A2)]])
t.key(Q, ESC); t.done()

t = open_mine()
t.key(UP, UP, ESC, BS); t.settle()
same("Backspace on a block selected inside a quote: gone from the quote's source", kids(A), [("quote", B), "alpha one"])
t.key(Z); t.settle()
same("  ^Z puts it back", kids(A), [("quote", B), "alpha one", "alpha two"])
t.key(Q, ESC); t.done()

t = open_mine({"quote": P})   # a quote of one block of text: the block you're in is the quote
t.key(UP, UP, ESC)
check("inside a quote of one block of text, Esc selects the quote", "block" not in bar(t) and "Plain" in bar(t), bar(t))
t.key(Q, ESC); t.done()

d = S.block_draft(B_(), A) if os.path.exists("t/qblocks.json") else ""
t = open_mine({"quote": A, "mask": [d.index("alpha one"), d.index("alpha two") + 5]})
t.key(UP, UP, ESC)   # a masked view: no blocks selected whole there yet
check("in a masked view, Esc selects the quote, not a block", "block" not in bar(t) and "Alpha" in bar(t), bar(t))
t.key(Q, ESC); t.done()
F.report("QBLOCKS")
