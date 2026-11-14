# masking through a quote: the quotes inside what it shows, each masked as seen through it (`inner`)
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, UP, DOWN, HOME, END, ESC, MENU, UNDO as Z
S = F.use_store("t/store.json")
A, A1, QAB, A2, B, B1, B2, QAC, C, C1 = ["20261001T100000-aa%02d" % n for n in range(10)]
ME, X, Q = ["20261021T230000-ff%02d" % n for n in range(3)]
def fresh(qab=None):
    F.write_store([blk(A, [A1, QAB, A2], "Alpha"), blk(A1, "alpha opens"), blk(QAB, qab or {"quote": B}), blk(A2, "alpha closes"),
                   blk(B, [B1, B2], "Beta"), blk(B1, "beta one"), blk(B2, "beta two"),
                   blk(ME, [X, Q], "mine"), blk(X, "x"), blk(Q, {"quote": A})], [A, B, ME])
    S.cmd_migrate(None)
    F.write_meta(ME); open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
def Term(): return F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=50, rows=18)
def blocks(): return S.index(S.load_data())
def content(i): return blocks()[i]["content"]
def bdraft(): return S.block_draft(blocks(), B)
TWO = lambda: [bdraft().index("beta two"), bdraft().index("beta two") + 8]
INTO_BETA = (DOWN, MENU, "create", "\r", DOWN)   # select the quote, masking mode, down: straight into Beta's box

fresh(); t = Term()
t.key(DOWN, MENU)
check("on a quote with no mask the menu says Create mask", "Create mask" in t.text() and "Edit mask" not in t.text(), t.text())
t.key("create", "\r", DOWN)
check("masking mode: arrowing into a box inside masks it, shown whole: no brackets drawn there (they go without saying)", "beta one" in t.text() and "beta two" in t.text() and "‹beta" not in t.text() and "two›" not in t.text(), t.text())
check("  while the quote where masking started draws its own, implied ones too", "‹alpha opens" in t.text() and "alpha closes›" in t.text(), t.text())
check("  the status bar never switches to the box the cursor's in", "Beta" not in t.row(17), t.row(17))
row = next(y for y in range(18) if "alpha opens" in t.row(y))
x = t.row(row).index("‹")
check("  the implied bracket where masking started is drawn dim, not bold", t.cell(row, x).fg == "red" and not t.cell(row, x).bold, t.cell(row, x))
t.key("zz"); t.settle()
check("  no typing in masking mode", S.own_text(blocks(), B) == "beta one\nbeta two" and "no typing" in t.text(), S.own_text(blocks(), B))
t.key(DOWN, HOME, "["); t.settle()
check("  [ at 'beta two' acts on the flow: everything before it hides, Alpha's own text too", "mask" in content(Q) and content(Q).get("inner") == {QAB: TWO()}, content(Q))
check("    stored per block, on my quote: its own mask and an inner one for Beta", content(Q)["mask"][0] > 0, content(Q))
check("  drawn: just the ‹ you typed, not the › implied at the end", "‹beta two" in t.text() and "two›" not in t.text(), t.text())
check("  the source is untouched: Alpha's quote of Beta has no mask", content(QAB) == {"quote": B}, content(QAB))
t.key(UP, UP); t.settle()   # back out into Alpha's text, still masking
check("  out of Beta's box, still masking: its hidden text stays, dim, until the whole mask is done", "beta one" in t.text() and "‹beta two" in t.text(), t.text())
y1 = next(y for y in range(18) if "beta one" in t.row(y))
check("    dim", t.cell(y1, t.row(y1).index("beta one")).fg != "red" and not t.cell(y1, t.row(y1).index("beta one")).bold, t.row(y1))
t.key(ESC); t.settle()
check("Esc: done; shown from 'beta two' on: not 'alpha opens', not 'beta one'", "beta two" in t.text() and "beta one" not in t.text() and "alpha opens" not in t.text() and "alpha closes" in t.text(), t.text())
check("  my entry's words count what it shows", blocks()[ME]["words"] == 1 + 2 + 2, blocks()[ME]["words"])
t.key(Z); t.settle()
check("one ^Z (right after finishing) undoes the whole mask edit, inner masks and all", "inner" not in content(Q) and "beta one" in t.text(), (content(Q), t.text()))
t.key(F.REDO); t.settle()
check("  ^Y puts it back", content(Q).get("inner") == {QAB: TWO()}, content(Q))
t.key(MENU)
check("Remove mask is offered from inside the quote too", "Remove mask" in t.text() and "Edit mask" in t.text(), t.text())
t.key(ESC, ESC, MENU)   # out of Alpha's view: my quote selected
check("now the menu says Edit mask", "Edit mask" in t.text() and "Create mask" not in t.text(), t.text())
t.close()

fresh(); t = Term()
t.key(DOWN, MENU, "create", "\r", END, *["\x1b[D"] * 5, "[")   # in Alpha's text: [ before "opens"
t.key(DOWN, END, "]"); t.settle()                             # straight into Beta's box: ] after "beta one"
one = [bdraft().index("beta one"), bdraft().index("beta one") + 8]
check("brackets in the flow land per block: my quote's own mask, and its inner one for Beta", content(Q).get("mask") is not None and content(Q).get("inner") == {QAB: one}, content(Q))
t.key(ESC); t.settle()
check("  together they read as one span: from 'opens' to 'beta one', nothing after", "opens" in t.text() and "alpha opens" not in t.text() and "beta one" in t.text() and "beta two" not in t.text() and "alpha closes" not in t.text(), t.text())
t.key(ESC, ESC, MENU, "remove", "\r"); t.settle()
check("Remove mask clears it all, inner masks too", "mask" not in content(Q) and "inner" not in content(Q) and "alpha opens" in t.text() and "beta two" in t.text(), content(Q))
t.close()

fresh()
d = S.block_draft(blocks(), B); i = d.index("beta two")
F.write_store([blk(A, [A1, QAB, A2], "Alpha"), blk(A1, "alpha opens"), blk(QAB, {"quote": B, "mask": [i, i + 8]}), blk(A2, "alpha closes"),
               blk(B, [B1, B2], "Beta"), blk(B1, "beta one"), blk(B2, "beta two"),
               blk(ME, [X, Q], "mine"), blk(X, "x"), blk(Q, {"quote": A})], [A, B, ME])
S.cmd_migrate(None); open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
t = Term()
t.key(DOWN)   # my quote of Alpha selected: Beta's … (Alpha's quote's own mask) is a level down
y = next(y for y in range(18) if "…" in t.row(y))
check("a … red only at the top level of the block the status bar names: Beta's, a box down, dim", t.cell(y, t.row(y).index("…")).fg != "red", t.row(y))
t.key(DOWN, DOWN)   # into Alpha, onto Beta's quote
check("  red with Beta's quote selected", t.cell(y, t.row(y).index("…")).fg == "red", t.row(17))
t.key(ESC, ESC)
t.close(); t = Term()
t.key(*INTO_BETA)
check("what the source already hides is a locked … while masking: 'beta one' stays out of sight", "beta one" not in t.text() and "…" in t.text() and "beta two" in t.text() and "‹beta two" not in t.text(), t.text())
t.key(DOWN, HOME, *["\x1b[C"] * 5, "]", ESC); t.settle()   # ] after "beta": hide " two"
check("  masking can only hide more: 'beta' shows, nothing else of Beta", "beta" in t.text() and "beta two" not in t.text() and "beta one" not in t.text(), t.text())
check("  the flow: what came before shows, what comes after doesn't", "alpha opens" in t.text() and "alpha closes" not in t.text(), t.text())
t.close()

fresh(); t = Term()
t.key(DOWN, DOWN, DOWN, MENU, "create", "\r", DOWN, HOME, "[", ESC); t.settle()   # into Alpha first, then mask Beta's quote there
check("started from inside, on the inner quote: that quote's own mask (edit-through), not mine", content(QAB).get("mask") == TWO() and "inner" not in content(Q), (content(QAB), content(Q)))
t.close()

fresh(); t = Term()
t.key(*INTO_BETA, DOWN, HOME, "[", ESC); t.settle()
S.commit(B, bdraft().replace("beta one", "beta one, longer"), [])
check("an edit of Beta moves my inner mask along: still 'beta two'", content(Q)["inner"][QAB] == TWO(), (content(Q)["inner"], TWO()))
t.close()
# an entry ending (or starting) with a quote: a mask can still show it
d = "{{block a}}\ntesting here\n{{quote " + B + " " + QAB + "}}"
check("a span can end after a quote the text ends with", S.snap(d, len(d), False) == len(d) and S.normalize(d, [S.snap(d, 0, True), len(d)]) is None)
d2 = "{{quote " + B + " " + QAB + "}}\n{{block a}}\ntext"
check("  and start before one it starts with", S.snap(d2, 0, True) == 0 and S.normalize(d2, [0, len(d2)]) is None)
F.write_store([blk(A, [A1, QAB], "Alpha"), blk(A1, "alpha opens"), blk(QAB, {"quote": B}),
               blk(B, [B1, B2], "Beta"), blk(B1, "beta one"), blk(B2, "beta two"),
               blk(ME, [X, Q], "mine"), blk(X, "x"), blk(Q, {"quote": A})], [A, B, ME])
S.cmd_migrate(None); open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
t = Term()
t.key(DOWN, MENU, "create", "\r")
check("masking a quote whose text ends with a quote: its opener drawn, the closer (on the quote line) goes without saying", "‹alpha opens" in t.text() and "alpha opens›" not in t.text(), t.text())
t.key(ESC); t.settle()
check("  finishing with everything shown keeps the quote at the end", "mask" not in content(Q) and "beta two" in t.text(), (content(Q), t.text()))
t.close()
# a quote inside that ends up showing nothing: no empty box, one …
F.write_store([blk(A, [A1, QAB, QAC, A2], "Alpha"), blk(A1, "alpha opens"), blk(QAB, {"quote": B}), blk(QAC, {"quote": C}), blk(A2, "alpha closes"),
               blk(B, [B1, B2], "Beta"), blk(B1, "beta one"), blk(B2, "beta two"), blk(C, [C1], "Gamma"), blk(C1, "gamma text"),
               blk(ME, [X, Q], "mine"), blk(X, "x"), blk(Q, {"quote": A})], [A, B, C, ME])
S.cmd_migrate(None); open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
t = Term()
t.key(*INTO_BETA, END, "]", ESC, ESC); t.settle()   # ] after "beta one": Beta's second line, Gamma and "alpha closes" hide
check("] in one of two quotes side by side: the next one hides whole (an inner mask showing nothing)", content(Q)["inner"].get(QAC) == [] and "gamma text" not in t.text(), (content(Q), t.text()))
check("  drawn as one …, no empty box", sum(("┌" in t.row(y) or "┏" in t.row(y)) for y in range(18)) == 4 and t.inside(10) == "…", t.text())  # x, my quote, alpha opens, Beta
t.close()
F.report("NESTMASK")
