# Ctrl+Enter: a block inside the block, split at the cursor; Enter on an empty one inside steps back out
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, END, LEFT, ENTER, BS, QUIT as Q, UNDO as Z
S = F.use_store("t/subblock.json", clean=True)
HOST, H1, X = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
CE = "\x1b[13;5u"   # Ctrl+Enter (kitty protocol)
def fresh():
    F.write_store([blk(HOST, [H1, X], "host"), blk(H1, "abcdef"), blk(X, "end")], [HOST], version=9)
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def kids(i, b=None):
    b = b or B()
    return [kids(k, b) if S.children(b[k]) else b[k]["content"] for k in S.children(b[i])]
def snap(): return json.dumps(sorted((b["id"], b["content"]) for b in S.load_data()["blocks"]), default=str)
def open_(): return F.fw("host", rows=30, cols=60)

fresh()
t = open_()   # at the end of "end"
t.key(UP, END, LEFT * 3, CE); t.settle()
same("Ctrl+Enter mid-text: the block holds its text either side, a level down", kids(HOST), [["abc", "def"], "end"])
check("  the block keeps its id, now a container", S.children(B()[HOST])[0] == H1 and len(S.children(B()[H1])) == 2)
t.key("X"); t.settle()
same("  the cursor at the start of the second", kids(HOST), [["abc", "Xdef"], "end"])
t.key(END, CE, "deep"); t.settle()
same("Ctrl+Enter inside a block inside: a level deeper", kids(HOST), [["abc", ["Xdef", "deep"]], "end"])
t.key(ENTER, "same"); t.settle()
same("Enter in there: a sibling at that level", kids(HOST), [["abc", ["Xdef", "deep", "same"]], "end"])
t.key(ENTER, ENTER, "up one"); t.settle()
same("Enter on an empty one: out a level, after its container", kids(HOST), [["abc", ["Xdef", "deep", "same"], "up one"], "end"])
t.key(ENTER, ENTER, "top"); t.settle()
same("  and again: out to the entry's level", kids(HOST), [["abc", ["Xdef", "deep", "same"], "up one"], "top", "end"])
t.key(Q, ESC := "\x1b"); t.done()
t = open_()
t.settle()
same("reopened: the nesting is just as it was", kids(HOST), [["abc", ["Xdef", "deep", "same"], "up one"], "top", "end"])
check("  drawn: boxes in boxes", "│││" in t.text() or "││ │" in t.text(), t.text())
t.key(Q, ESC); t.done()

fresh(); before = snap()
t = open_()
t.key(UP, END, LEFT * 3, CE, "typed"); t.settle()
t.key(Z, Z); t.settle()
same("^Z after Ctrl+Enter and typing: the store as it was", snap(), before)
t.key(Q, "\x1b"); t.done()

fresh()
t = open_()
t.key(UP, END, LEFT * 3, CE, BS); t.settle()
same("Backspace at the start of the new one joins it back", kids(HOST), ["abcdef", "end"])
t.key("!"); t.settle()
same("  and the joined block still takes edits", kids(HOST), ["abc!def", "end"])
check("  nothing refused", "refus" not in t.text() and "isn't supported" not in t.text(), t.text())
t.key(Q, "\x1b"); t.done()

fresh()
t = open_()
t.key(ENTER, CE, "child"); t.settle()   # an empty, never-saved block
same("Ctrl+Enter on a new empty block: a container of one run of text is that text (as ever)", kids(HOST), ["abcdef", "end", "child"])
t.key(ENTER, ENTER, "after"); t.settle()
same("  Enter twice: a sibling inside, then out", kids(HOST), ["abcdef", "end", "child", "after"])
t.key(Q, "\x1b"); t.done()
QH, QQ, QX, SRC, S1 = "20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002", "20261001T100000-5000", "20261001T100000-5001"
F.write_store([blk(QH, [QQ, QX], "qhost"), blk(QQ, {"quote": SRC}), blk(QX, "end"), blk(SRC, [S1], "src"), blk(S1, "abcdef")], [QH, SRC], version=9)
S.cmd_migrate(None)
t = F.fw("qhost", rows=30, cols=60)
t.key(UP, UP, END, LEFT * 3, CE, "Y"); t.settle()
same("inside a quote, Ctrl+Enter nests in its source (edit-through)", kids(SRC), [["abc", "Ydef"]])
check("  the quote's own entry is untouched", S.children(B()[QH]) == [QQ, QX], kids(QH))
t.key(Q, "\x1b"); t.done()
def boxes(t, word):
    """How many boxes `word` is drawn inside: the box corners left of it on its row."""
    y = t.find(word); row = t.text().split("\n")[y]
    return row[:row.index(word)].count("│")
fresh()
t = open_()
t.key(UP, END, LEFT * 3, CE); t.settle()
same("split: abc and def each in a box inside the block's", boxes(t, "def"), 2)
t.key(BS); t.settle()
same("joined back: one block of text left, so no box inside, as it was", boxes(t, "abcdef"), 1)
same("  stored as plain text, under the block's own id", (kids(HOST), S.children(B()[HOST])[0]), (["abcdef", "end"], H1))
t.key("!"); t.settle()
same("  and it takes edits", kids(HOST), ["abc!def", "end"])
t.key(Q, "\x1b"); t.done()

T, D, E, E1, E2 = (f"20261001T100000-e00{n}" for n in range(5))
F.write_store([blk(HOST, [T, H1], "host"), blk(T, "top"), blk(H1, [D, E]), blk(D, "abc"), blk(E, [E1, E2]), blk(E1, "x"), blk(E2, "y")], [HOST], version=9)
S.cmd_migrate(None)
t = open_()   # at the end of "y"
same("a block holding abc and a block of x and y", kids(HOST), ["top", ["abc", ["x", "y"]]])
t.key(UP, UP, END, BS * 4); t.settle()
same("abc emptied and joined into top: the block holds one container, whose blocks move up into it", kids(HOST), ["top", ["x", "y"]])
check("  the one inside is gone, the block keeps its id", S.children(B()[HOST])[1] == H1 and E not in B(), S.children(B()[H1]))
same("  drawn a level less deep", boxes(t, "x"), 2)
t.key(Q, "\x1b"); t.done()
F.report("SUBBLOCK")
