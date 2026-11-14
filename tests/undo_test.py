# undo of whole actions: pop out, detach, show all, a mask edit
import sys
sys.path.insert(0, ".")
exec(open("maskui_test.py").read().split("# --- checks")[0])   # fresh(), Term, ids, helpers
from fwtest import REDO as Y

fresh(); before = state(); t = Term()
t.key(MENU, "\r"); t.settle()                 # on "x": Turn into a quote
popped = state()
t.key(Z); t.settle()
check("pop out, then ^Z: as if it never happened (no new entry, no new block)", state() == before, diff(before, state()))
y = t.find("x")
check("  the screen shows the text block again", y is not None and t.cell(y - 1, 0).data == "1" and t.cell(y - 1, 0).bg != "red", t.text())
t.key(Y); t.settle()
check("^Y pops it out again", len(state()[0]) == len(before[0]) + 1 and S.quoted(B()[T]), diff(popped, state()))
t.close()

fresh([qk, br]); before = state(); t = Term()
t.key(DOWN, MENU, "turn", "\r"); t.settle()    # Turn into text
t.key(Z); t.settle()
check("detach, then ^Z: the quote is back, mask and all", state() == before, diff(before, state()))
y = t.find("…quick brown…")
check("  and shows as a quote again", y is not None and t.cell(y - 1, 0).bg == "red", t.text())
t.close()

fresh([qk, br]); before = state(); t = Term()
t.key(DOWN, MENU, "remove", "\r")
t.key(Z); t.settle()
check("show all, then ^Z: the mask is back", state() == before, diff(before, state()))
t.close()

fresh(); before = state(); t = Term()
t.key(DOWN, DOWN, MENU, "\r", HOME, RIGHT * 5, *[SRIGHT] * 11, "[", ESC)   # mask to "quick brown"
masked = state()
t.key(Z); t.settle()
check("a mask edit, then ^Z: unmasked again", state() == before, diff(before, state()))
check("  and the quote shows all of its text", "the quick brown fox" in t.text(), t.row(1))
t.key(Y); t.settle()
check("^Y masks it again", state() == masked, diff(masked, state()))
t.close()

F.report("UNDO")
