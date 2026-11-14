# blocks selected whole (fw_blocks): Esc, Shift+↑/↓, a text selection snapping to blocks, and acting on them
import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ESC, BS, QUIT as Q, UNDO as Z
S = F.use_store("t/blocks.json", clean=True)
HOST, C1, QB, C3 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-b003"
OLD, CO = "20261001T100000-a000", "20261001T100000-a001"
SUP, SDOWN, COPY, CUT, PASTE, ALL = "\x1b[1;2A", "\x1b[1;2B", "\x03", "\x18", "\x16", "\x01"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/clip.txt")}  # never the real clipboard
def fresh():
    F.write_store([blk(HOST, [C1, QB, C3], "host"), blk(C1, "one"), blk(QB, {"quote": OLD}), blk(C3, "three"),
                   blk(OLD, [CO], "old note"), blk(CO, "old text")], [HOST, OLD])
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())
def kids(i=HOST):  # the entry's blocks: text, a quote's target, or a container's, as a list
    b = B()
    return [S.quoted(b[k])[0] if S.quoted(b[k]) else kids(k) if S.children(b[k]) else b[k]["content"]
            for k in S.children(b[i])]
def bar(t): return t.row(t.scr.lines - 1)
def open_host():
    fresh()
    return F.fw("host", rows=24, env=ENV)

t = open_host()  # the cursor starts at the end of "three"
t.key(ESC)
check("Esc selects the block you're in whole", "block 3" in bar(t), bar(t))
check("  its top edge heavy", any("┏" in t.row(y) for y in range(t.scr.lines)), t.text())
y, x = next((y, x) for y in range(t.scr.lines) for x in range(t.scr.columns) if t.cell(y, x).underscore)
check("  the ghost: where ↓ lands, at the start of its text", "three" in t.row(y) and t.cell(y, x).data == "t",
      (t.row(y), x))
t.key(SUP)
check("Shift+↑ adds the block above (a quote)", "blocks 2–3" in bar(t), bar(t))
t.key(SUP)
check("  and the one above that", "blocks 1–3" in bar(t), bar(t))
t.key(SDOWN)
check("Shift+↓ takes one back off", "blocks 2–3" in bar(t), bar(t))
t.key(ESC)
check("Esc again: the cursor's back where it was", "3:6" in bar(t), bar(t))
t.key(Q, ESC); t.done()

t = open_host()
t.key(SUP)
check("a text selection reaching another block takes whole blocks", "blocks 2–3" in bar(t), bar(t))
t.key(SDOWN)
check("  back inside the block it began in, it's text again", "block" not in bar(t), bar(t))
t.key(Q, ESC); t.done()

t = open_host()
t.key(ESC, DOWN)
check("↓ from the heavy top edge goes inside, to the start", "block" not in bar(t) and t.cell(*t.cursor()).data == "t", bar(t))
t.key(ESC, UP)
check("↑ from it steps out: the quote above is selected", "old note" in bar(t), bar(t))
t.key(Q, ESC); t.done()

t = open_host()
t.key(ESC, SUP, SUP, BS); t.settle()
same("Backspace removes the blocks selected", kids(), [])
t.key(Z); t.settle()
same("  ^Z brings them all back", kids(), ["one", OLD, "three"])
t.key(Q, ESC); t.done()

t = open_host()
t.key(ESC, "new"); t.settle()
same("typing replaces the block with a new one", kids(), ["one", OLD, "new"])
check("  a block of its own", C3 not in S.children(B()[HOST]))
t.key(Q, ESC); t.done()

t = open_host()
t.key(ESC, SUP, SUP, SDOWN)  # from 3 up to 1, then back: blocks 2–3
t.key(COPY)
check("copy says how many blocks", "copied 2 blocks" in bar(t), bar(t))
same("  the Mac clipboard gets their text, a blank line apart", open("t/clip.txt").read(), "old text\n\nthree")
t.key(ESC)
t.key(ESC, SUP, CUT); t.settle()
same("cut takes them out", kids(), ["one"])
t.key(PASTE); t.settle()   # the cursor at the end of "one": in its text
same("paste after a cut, in a block's text: they move inside it; the block holds its text and them", kids(), [["one", OLD, "three"]])
check("  moved, not copied: the same blocks", C3 in S.subtree(B(), HOST) and QB in S.subtree(B(), HOST), S.subtree(B(), HOST))
t.key(Z); t.settle()
same("  ^Z: as it was", kids(), ["one"])
t.key(ESC, PASTE); t.settle()   # "one" selected whole, its top heavy
same("  pasted on a block selected from its top: before it", kids(), [OLD, "three", "one"])
t.key(Q, ESC); t.done()

t = open_host()
t.key(ESC, SUP, COPY, ESC, UP)   # blocks 2–3 copied; then back in "three", and up onto the quote, from below
t.key(PASTE); t.settle()
same("pasted on a quote the arrows selected from below: after it (^V: a copy of the quote, a quote of the block)", kids(), ["one", OLD, OLD, C3, "three"])
t.key(Q, ESC); t.done()

t = open_host()
t.key(ALL)
check("^A with several blocks selects them all whole", "blocks 1–3" in bar(t), bar(t))
t.key("\x14")  # Ctrl+T, Turn into a quote
check("  a command over several blocks says it acts on one", "select within one block" in bar(t), bar(t))
t.key(Q, ESC); t.done()

F.report("BLOCKS")
