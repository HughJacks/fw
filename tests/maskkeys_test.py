# editing a mask: Tab between brackets, Backspace on one, carrying one, typing
import sys
sys.path.insert(0, ".")
exec(open("maskui_test.py").read().split("# --- checks")[0])   # fresh(), Term, ids, helpers

fresh([qk, br, d.index("lazy"), d.index("lazy") + 8]); t = Term()
t.key(DOWN, DOWN, " ")             # past the leading …: Space edits the mask
t.key(HOME, TAB, TAB)               # to the second bracket (the › after brown)
check("Tab jumps just past the next bracket", t.row(t.scr.cursor.y)[t.scr.cursor.x - 1] == "›", (t.scr.cursor.x, t.row(t.scr.cursor.y)))
t.key(BS); t.settle()
check("Backspace on a bracket: the spans either side join", shown() == ["quick brown fox\njumps over the lazy dog"], shown())
t.key(Z); t.settle()
check("^Z inside the mask edit undoes one step", shown() == ["quick brown", "lazy dog"], shown())
t.key(BTAB)
check("Shift+Tab jumps back", t.row(t.scr.cursor.y)[t.scr.cursor.x - 1] in "‹›", (t.scr.cursor.x, t.row(t.scr.cursor.y)))
t.close()

fresh([qk, br]); t = Term()
t.key(DOWN, DOWN, END, " ")         # mask edit, cursor after the ›
t.key(BS, RIGHT, RIGHT, RIGHT, RIGHT, "]"); t.settle()   # moving a bracket: Backspace on it, ] further on
check("a bracket moves by typing: Backspace takes it out, ] puts one further on", shown() == ["quick brown fox"], shown())
t.key(HOME, "and "); t.settle()
check("no typing in masking mode: the text stays as it was", S.own_text(B(), A).startswith("the quick") and "no typing" in t.text(), S.own_text(B(), A)[:20])
t.key(ESC, Z); t.settle()
check("Esc, then ^Z: the whole mask edit undone", mask() == [qk, br] and S.own_text(B(), A).startswith("the quick"), (mask(), S.own_text(B(), A)[:20]))
t.close()

F.report("MASKKEYS")
