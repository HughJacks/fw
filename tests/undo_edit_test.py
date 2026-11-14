# undo of edits: moving a bracket, deleting a masked quote, typing in a view, pop out then type
import sys
sys.path.insert(0, ".")
exec(open("maskui_test.py").read().split("# --- checks")[0])   # fresh(), Term, ids, helpers

fresh([qk, br]); t = Term()
t.key(DOWN, DOWN, END, " ", BS, RIGHT, RIGHT, RIGHT, RIGHT, "]"); t.settle()  # move the › 4 right, by typing
moved = shown()
t.key(Z, Z); t.settle()
check("move a bracket, then ^Z ^Z: the mask is back where it was", (moved, shown()) == (["quick brown fox"], ["quick brown"]), (moved, shown()))
t.close()

fresh([qk, br]); before = state(); t = Term()
t.key(DOWN, BS); t.settle()                    # select the masked quote, delete it (saved: its block is erased)
gone = QM not in B()
t.key(Z); t.settle()
check("delete a masked quote, then ^Z: back with its mask", gone and state() == before, diff(before, state()))
t.close()

fresh([qk, br]); t = Term()
t.key(DOWN, DOWN, "new "); t.settle()          # type in the view
t.key(Z, Z); t.settle()                        # the space, then the word
check("typing in a view undoes word by word", shown() == ["quick brown"] and S.own_text(B(), A).startswith("the quick"), (shown(), S.own_text(B(), A)[:20]))
t.close()

fresh(); before = state(); t = Term()
t.key(MENU, "\r"); t.settle()                  # pop out "x"
t.key("m"); t.settle()                         # then write something else (below it)
t.key(Z, Z); t.settle()
check("pop out, type, then ^Z ^Z: both undone, nothing left over", state() == before, diff(before, state()))
t.close()
F.report("UNDOEDIT")
