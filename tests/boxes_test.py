import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, UP, DOWN, END
S = F.use_store("t/boxes.json", clean=True)
ME, X, Q1 = "20261021T230000-0000", "20261021T230000-0001", "20261021T230000-0002"
A, A1, QAB = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
B, B1, QBC = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
C, C1, C2 = "20261001T100000-c000", "20261001T100000-c001", "20261001T100000-c002"
CT, T1, QT, T2, P = ("20261021T230000-0010", "20261021T230000-0011", "20261021T230000-0012",
                     "20261021T230000-0013", "20261001T100000-d000")
SOFT, FAINT = "875f5f", "4e4e4e"   # a quote's box at rest, a block of text's
def Term(rows=30): return F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=50, rows=rows)
def start(blocks, mine):
    F.write_store(blocks + [blk(ME, mine, "mine")], [A, B, C, P, ME])
    S.cmd_migrate(None)
    F.write_meta(ME)
    open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
def row_of(t, text): return t.find(text)
def screen(t): return [t.row(y) for y in range(t.scr.lines - 1)]   # (not the status bar)

# a quote of a quote of a quote, each of several blocks: every block boxed, as deep as there's room
start([blk(A, [A1, QAB], "Alpha"), blk(A1, "alpha"), blk(QAB, {"quote": B}),
       blk(B, [B1, QBC], "Beta"), blk(B1, "beta"), blk(QBC, {"quote": C}),
       blk(C, [C1, C2], "Gamma"), blk(C1, "gamma one"), blk(C2, "gamma two"),
       blk(X, "x"), blk(Q1, {"quote": A})], [X, Q1])
t = Term()
rest = screen(t)
y = row_of(t, "alpha")
check("a quote's blocks of text each in a faint box inside it", t.cell(y - 1, 3).data == "┌" and t.cell(y - 1, 3).fg == FAINT and t.cell(y + 1, 3).data == "└", rest)
y = row_of(t, "beta")
check("  and a level deeper, inside the quote inside it", t.cell(y - 1, 4).data == "┌" and t.cell(y - 1, 4).fg == FAINT, rest)
y = row_of(t, "gamma one")
check("  with no room left for a box: unboxed, a dot before each block, where a box's side would be", t.cell(y, 5).data == "·" and t.cell(y + 1, 5).data == "·" and t.inside(y + 1) == "·gamma two" and t.cell(y, 6).data == "g", rest)
t.key(DOWN, DOWN)   # the quote selected, then in, past alpha's box top
check("into the quote: the cursor in its first block's text, over its box's top", t.cursor() == (row_of(t, "alpha"), 6), (t.cursor(), screen(t)))
check("  nothing moved", screen(t) == rest, screen(t))
t.key(DOWN)
y = row_of(t, "beta") - 2
check("Down: over alpha's box bottom, onto the quote inside, selected", t.cell(y, 3).data == "┏", (y, screen(t)))
t.key(DOWN)
check("  Down again: into it, over beta's box top", t.cursor() == (row_of(t, "beta"), 6), (t.cursor(), screen(t)))
t.key(DOWN, DOWN, DOWN)   # Gamma selected, in it (no box for its blocks), gamma two
check("  and into the deepest: its blocks dotted, the cursor among them", t.cursor() == (row_of(t, "gamma two"), 6), (t.cursor(), screen(t)))
check("  still nothing moved", [r.replace("┏", "┌").replace("━", "─").replace("┓", "┐") for r in screen(t)] == rest, screen(t))
t.close()

# a container in the entry: its text before and after the quote each in a box inside its box
start([blk(P, "plain body", "Plain"), blk(T1, "before"), blk(QT, {"quote": P}), blk(T2, "after"),
       blk(CT, [T1, QT, T2]), blk(X, "x")], [X, CT])
t = Term()
y = row_of(t, "before")
check("a container's blocks boxed inside its box: text faint, the quote red", t.cell(y - 2, 2).data == "┌" and t.cell(y - 1, 3).data == "┌" and t.cell(y - 1, 3).fg == FAINT and t.cell(y + 2, 3).fg == SOFT and t.inside(y + 3) == "plain body", screen(t))
check("  one number for the container", t.row(y - 2).startswith("2 ") and not t.row(y - 1)[0].isdigit(), screen(t))
t.key(DOWN)
check("Down from x: into the container's first block, over two box tops", t.cursor() == (y, 6), (t.cursor(), screen(t)))
t.key(DOWN)
check("  Down: the quote in it selected", t.cell(y + 2, 3).data == "┏", screen(t))
t.key(DOWN, DOWN, DOWN)   # in, its bottom selected, on
check("  through it, over its box bottom and the next box's top: on after", t.cursor() == (row_of(t, "after"), 6), (t.cursor(), screen(t)))
t.key(F.ESC)
check("Esc selects the container whole: its boxes lit, the quote's too", t.cell(y - 2, 2).bold and t.cell(y - 1, 3).bold and t.cell(y + 2, 3).bold, screen(t))
t.close()

# a quote of one block of text: just the quote's box, as before
start([blk(P, "plain body", "Plain"), blk(X, "x"), blk(Q1, {"quote": P})], [X, Q1])
t = Term()
y = row_of(t, "plain body")
check("a quote of one block of text: no box inside the quote's", t.cell(y - 1, 2).data == "┌" and t.cell(y - 1, 3).data == "─", screen(t))
t.close()
F.report("BOXES")
