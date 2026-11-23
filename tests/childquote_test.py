# quoting any block, not just entries: the quote search shows the blocks inside entries; Open it goes
# to the entry a block lives in; taking a quoted block out turns its quotes into text, undone with it
import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ESC, BS, ENTER, QUIT as Q, UNDO as Z
S = F.use_store("t/childquote.json", clean=True)
NOTES, N1, N2, N3 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002", "20261001T100000-a003"
ME, X, QP = "20261002T100000-b000", "20261002T100000-b001", "20261002T100000-b0aa"
CTRL_O = "\x0f"
def fresh():
    F.write_store([blk(NOTES, [N1, N2, N3], "notes"), blk(N1, "first idea"), blk(N2, "second idea about bowling"),
                   blk(N3, "third"), blk(ME, [X], "mine"), blk(X, "x")], [NOTES, ME])
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def kids(i):
    b = B()
    return [("quote", S.quoted(b[k])[0]) if S.quoted(b[k]) else b[k]["content"] for k in S.children(b[i])]
def bar(t): return t.row(t.scr.lines - 1)

fresh()
t = F.fw("mine", rows=30)   # at the end of "x"
t.key(ENTER, "/", ENTER, "bowl")
check("the quote search shows a block inside an entry whose title matches, indented under its entry",
      "notes" in t.text() and "  · second idea about bowling" in t.text(), t.text())
check("  not the blocks that don't match", "first idea" not in t.text() and "third" not in t.text(), t.text())
t.key(DOWN)   # past the entry, onto the block
check("  the bottom line says what Enter and Shift+Enter do", "its own pericope" in t.text() and "masked to it" in t.text(), t.text())
t.key(ENTER); t.settle()
k = kids(ME)
made = k[1][1] if len(k) > 1 and k[1][0] == "quote" else None
check("Enter: it becomes an entry of its own, quoted here", made and B()[made].get("entry") and made != NOTES, k)
same("  and quoted where it was", kids(NOTES), ["first idea", ("quote", made), "third"])
same("  holding the block's text", [B()[c]["content"] for c in S.children(B()[made])] if made else None, ["second idea about bowling"])
t.key(Z); t.settle()
same("^Z: back as it was, both places", (kids(NOTES), kids(ME)), (["first idea", "second idea about bowling", "third"], ["x"]))
check("  the entry gone", made not in B())
t.key(ENTER, "/", ENTER, "bowl", DOWN, F.SENTER if hasattr(F, "SENTER") else "\x1b[13;2u"); t.settle()
k = kids(ME)
q = next((c for c in S.children(B()[ME]) if S.quoted(B()[c])), None)
check("Shift+Enter: a quote of its entry, masked to just that block", q and S.quoted(B()[q])[0] == NOTES and S.quoted(B()[q])[1], k)
check("  it shows that block, not the others", "second idea about bowling" in t.text() and "first idea" not in t.text() and "third" not in t.text(), t.text())
same("  the entry as it was", kids(NOTES), ["first idea", "second idea about bowling", "third"])
t.key(Z); t.settle()
check("  ^Z: gone", not any(S.quoted(B()[c]) for c in S.children(B()[ME])), kids(ME))
t.key(Q, ESC); t.done()

# a quote of the block itself (as ^V of copied blocks makes)
fresh()
def put_quote(data, blocks):
    S.add_block(data, blocks, QP, {"quote": N2}); blocks[ME]["content"].append(QP)
S.transact(S.editing(put_quote))
t = F.fw("mine", rows=30)   # at the end of "x"... below it, the quote
same("a quote of the block, not its entry", kids(ME), ["x", ("quote", N2)])
t.key(DOWN, DOWN); t.settle()
t.key(UP, UP, F.END, "!"); t.settle()   # onto the quote from below, into it; at its end
check("typing in it edits the block, where it lives", B()[N2]["content"] == "second idea about bowling!", B()[N2]["content"])
t.key(ESC, CTRL_O)   # the quote selected; Open it
check("Open it on a quote of a block in an entry: that entry, the trail back here", "mine ›" in bar(t) and "first idea" in t.text(), bar(t))
check("  the cursor at the block", " 2:1" in bar(t), bar(t))
t.key(ESC, BS); t.settle()   # select it whole, and take it out
check("taking the quoted block out of its entry: gone from it", kids(NOTES) == ["first idea", "third"], kids(NOTES))
same("  its quote elsewhere keeps the last of what it showed, as text", kids(ME), ["x", "second idea about bowling!"])
t.key(Z); t.settle()
same("^Z: the block back in its entry", kids(NOTES), ["first idea", "second idea about bowling!", "third"])
same("  and its quote a quote again, of it", kids(ME), ["x", ("quote", N2)])
t.key(Q, Q, ESC); t.done()

fresh()
t = F.fw("mine", rows=30)
t.key(ENTER, "/", ENTER)
check("with nothing typed, the quote search lists entries only", "notes" in t.text() and "· first idea" not in t.text(), t.text())
t.key(ESC, ESC, Q, ESC); t.done()
F.report("CHILDQUOTE")
