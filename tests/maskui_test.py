import os, re, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, UP, DOWN, LEFT, RIGHT, ESC, BS, HOME, END, TAB, BTAB, MENU, UNDO as Z
S = F.use_store("t/store.json")
A, CA, CB, ME, T, QM = ("20261001T100000-aaaa", "20261001T100000-c0a0", "20261001T100000-c0b0",
                        "20261021T230000-0000", "20261021T230000-c001", "20261021T230000-9999")
def fresh(mask=None):
    q = {"quote": A} if mask is None else {"quote": A, "mask": mask}
    F.write_store([blk(A, [CA, CB], "Alpha"), blk(CA, "the quick brown fox"), blk(CB, "jumps over the lazy dog"),
                   blk(ME, [T, QM], "mine"), blk(T, "x"), blk(QM, q)], [A, ME])
    F.write_meta(ME)
    B = S.index(S.load_data())
    open("t/f.txt", "w").write(S.block_draft(B, ME))
    return S.block_draft(B, A)
def B(): return S.index(S.load_data())
def adraft(): return S.block_draft(B(), A)
def mask(): q = S.quoted(B().get(QM)); return q[1] if q else "not a quote"
def shown():  # the shown text of each span (block markers left out)
    d, m = adraft(), mask()
    return [re.sub(r"\{\{block[^}]*\}\}\n", "", d[a:b]) for a, b in zip(m[0::2], m[1::2])] if isinstance(m, list) else m
def Term(): return F.editor("t/f.txt", "--meta", "t/f.meta.json")
SRIGHT = "\x1b[1;2C"
def state():
    """The store as it matters: the entries, and every block's content."""
    d = S.load_data()
    return sorted(S.entry_ids(d)), {b["id"]: b["content"] for b in d["blocks"]}
def diff(a, b):
    ea, ba = a; eb, bb = b
    return {"entries": (ea, eb)} if ea != eb else {} | {i: (ba.get(i), bb.get(i)) for i in set(ba) | set(bb) if ba.get(i) != bb.get(i)}
d = fresh(); qk, br = d.index("quick"), d.index("brown") + 5
# --- checks (the mask and undo suites run everything above this line)

# (rows found by their text, so a change of layout doesn't move the checks: t.lines(), t.find())
def quote(): return t.lines()[1:]   # what reads in the quote, after the entry's own "x"
fresh([qk, br]); t = Term()
y = t.find("…quick brown…")
check("a masked quote shows only its shown part, … for the rest", quote() == ["…quick brown…"], t.text())
check("  its … dim while the status bar names another block (or none)", t.cell(y, 6).fg != "red" and t.cell(y, 18).fg != "red")
t.key(DOWN)
check("  red once it's the quote selected: its own top level", t.cell(y, 6).fg == "red" and t.cell(y, 18).fg == "red" and t.cell(y, 7).fg != "red")
t.key(DOWN, "very "); t.settle()
check("typing in the view edits the source, the shown range grows", shown() == ["very quick brown"], shown())
t.key(HOME, RIGHT, BS); t.settle()
check("Backspace can't delete a hidden stretch", S.own_text(B(), A).startswith("the very quick") and "space edits the mask" in t.text())
t.key(END, " ")
check("Space on … edits the mask: all the text, every span bracketed", quote() == ["the ‹very quick brown› fox", "jumps over the lazy dog"], quote())
y = t.find("the ‹very quick brown› fox")
check("  each block in its box", t.cell(y - 1, 3).data == "┌" and t.cell(t.find("jumps over the lazy dog") - 1, 3).data == "┌", t.text())
check("  hidden text dim, brackets red", t.cell(y, 6).fg != "red" and t.cell(y, 6 + quote()[0].index("‹")).fg == "red")
t.key(DOWN, HOME, "[")
check("[ in hidden text shows from there to the end", "‹jumps over the lazy dog›" in quote(), quote())
t.key(RIGHT * 5, "]"); t.settle()
check("] then hides the rest: two spans in one quote", shown() == ["very quick brown", "jumps"], shown())
t.key(ESC)
check("Esc: done, the quote reads with … for each hidden part", quote() == ["…very quick brown…", "jumps…"], quote())
check("  hidden text never runs two blocks together: the second keeps its box", t.cell(t.find("jumps…") - 1, 3).data == "┌", t.text())
t.key(HOME, BS); t.settle()   # at the start of "jumps": joining would glue it to the hidden " fox"
check("  Backspace at a block's start, after hidden text: refused", quote()[-1] == "jumps…" and shown() == ["very quick brown", "jumps"] and "space edits the mask" in t.text(), (quote(), shown()))
t.key(UP, END, "X"); t.settle()   # typed after the … at the end of the first block's line
check("  typing after a block's last … goes in that block, after its hidden text", shown() == ["very quick brown", "X\njumps"] and S.own_text(B(), CA).endswith("foxX"), (shown(), S.own_text(B(), CA)))
t.close()

fresh(); t = Term()
t.key(DOWN, DOWN, MENU)
check("Ctrl+/ in an unmasked quote offers Create mask", "Create mask" in t.text() and "Edit mask" not in t.text())
t.key("\r")
check("  everything shows, with a bracket at each end", quote()[0] == "‹the quick brown fox" and quote()[-1].endswith("lazy dog›"), quote())
t.key(HOME, RIGHT * 5, *[SRIGHT] * 11, "[", ESC)
check("select + [ shows exactly the selection", shown() == ["quick brown"] and quote() == ["…quick brown…"], (shown(), quote()))
t.close()

fresh(); t = Term()
t.key(DOWN, DOWN, MENU, "\r", HOME, RIGHT * 10, "]", ESC)
check("] at the cursor in shown text hides from there: start..cursor", shown() == ["the quick"], shown())
t.close()

fresh(); t = Term()
t.key(DOWN, DOWN, MENU, "\r", HOME, RIGHT * 5, *[SRIGHT] * 6, "]", ESC)
check("select + ] hides exactly the selection", shown() == ["the ", "brown fox\njumps over the lazy dog"], shown())
t.close()

fresh([qk, br]); t = Term()
t.key(DOWN, MENU)
check("on a masked quote the menu offers Edit mask, Remove mask and Turn into text", "Edit mask" in t.text() and "Create mask" not in t.text() and "Remove mask" in t.text() and "Turn into text" in t.text())
t.key("remove", "\r")
check("Remove mask: the mask is gone", mask() is None and "the quick brown fox" in t.text(), mask())
t.close()

fresh([qk, br]); t = Term()
t.key(DOWN, MENU, "turn", "\r"); t.settle()
check("Turn into text: a plain copy of what it showed", S.quoted(B()[QM]) is None and B()[QM]["content"] == "…quick brown…", B()[QM]["content"])
t.close()

fresh(); t = Term()
t.key(MENU)
check("on a text block the menu offers turn-into-a-quote", "Turn into a quote" in t.text())
t.key("\r"); t.settle()
q = S.quoted(B()[T])
check("Turn into a quote: the block now quotes a new entry holding its text", q and S.own_text(B(), q[0]) == "x" and q[0] in S.entry_ids(S.load_data()), q)
t.close()

fresh(); t = Term()
t.key(DOWN, DOWN, END, "\r", "/")
check("/ on an empty line still opens the menu with Quote a block", "Quote a block" in t.text())
t.close()
F.report("MASKUI")
