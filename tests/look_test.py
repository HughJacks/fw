import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, UP, DOWN, LEFT, RIGHT, ESC, END
S = F.use_store("t/store.json")
SELF, A, B = "20261021T230000-0000", "20261001T100000-aaaa", "20261002T100000-bbbb"
def fresh(*root):
    me = blk(SELF, [], "mine")
    blocks = [blk(A, [{"ref": "20261001T100000-ca00"}], "Alpha"), blk("20261001T100000-ca00", "alpha body"),
              blk(B, [{"ref": "20261002T100000-cb00"}, {"ref": A, "as": "quote"}], "Beta"), blk("20261002T100000-cb00", "beta"), me]
    for n, k in enumerate(root):
        if k.startswith("Q:"): me["content"].append({"ref": k[2:], "as": "quote"})
        else: cid = f"20261021T230000-c00{n}"; me["content"].append({"ref": cid}); blocks.append(blk(cid, k))
    json.dump({"schemaVersion": 4, "entries": [A, B, SELF], "blocks": blocks}, open("t/store.json", "w"))
    json.dump({"id": SELF, "fields": []}, open("t/f.meta.json", "w"))
    open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), SELF))
def Term(rows=10): return F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=40, rows=rows)
red = lambda c: c.bg == "red"
SOFT, FAINT = "875f5f", "4e4e4e"   # a quote's box at rest (muted red), a block of text's (grey)
side = lambda c: c.data == "│" and c.fg in ("red", SOFT)   # a quote's box side
# rows: 0-2 the box of "x", 3-5 the quote's (number on 3, text on 4), 6-8 "y"'s;
# all text from column 6, past room for 3 boxes (a column each)

fresh("x", "Q:" + A, "y"); t = Term()
check("every block in a box: text in a faint grey one", t.cell(0, 2).data == "┌" and t.cell(0, 2).fg == FAINT and t.inside(1) == "x" and t.cell(2, 2).data == "└", [t.row(0), t.row(1), t.row(2)])
check("  a quote in a muted red one at rest, its text inside", t.cell(3, 2).data == "┌" and t.cell(3, 2).fg == SOFT and t.inside(4) == "alpha body" and side(t.cell(4, 2)) and side(t.cell(4, 38)) and t.cell(5, 2).data == "└", [t.row(3), t.row(4), t.row(5)])
check("  numbers on the box tops: a quote's muted at rest, a text block's plain", t.cell(3, 0).fg == SOFT and not red(t.cell(3, 0)) and t.cell(3, 0).data == "2" and t.cell(0, 0).data == "1" and not red(t.cell(0, 0)) and t.cell(6, 0).data == "3")
check("  no old marks", not any(ch in t.text() for ch in "▀▄┃“"))
check("  not bright while not selected", not t.cell(4, 2).bold)
t.key(DOWN)
check("Down onto it: its top goes heavy (the end you're at), the box bright red", t.cell(3, 2).data == "┏" and t.cell(3, 3).data == "━" and t.cell(5, 2).data == "└" and t.cell(4, 2).bold and t.cell(4, 2).fg == "red", [t.row(3), t.row(5)])
check("  its number white on red", red(t.cell(3, 0)) and t.cell(3, 0).fg == "white")
g = t.cell(4, 6)
check("  outlined (white underline): where Down lands next", g.data == "a" and g.underscore and g.fg == "white", g)
t.key(DOWN)
check("Down again: inside, right where the outline was", t.cursor() == (4, 6) and t.cell(3, 2).data == "┌", t.cursor())
check("  inside: still bright, no outline", t.cell(4, 2).bold and not t.cell(4, 6).underscore)
t.key(ESC)
check("Esc: selected again, at its top", t.cell(3, 2).data == "┏")
t.close()

fresh("x", "Q:" + A, "y"); t = Term()
t.key(DOWN, DOWN, DOWN, DOWN)   # select, in, out (selected), past: on y
check("Down past a quote: on into the next block's text, over the boxes' edges", t.cursor() == (7, 6), t.cursor())
t.key(END, UP)
check("Up onto it from below: its bottom goes heavy", t.cell(5, 2).data == "┗" and t.cell(3, 2).data == "┌", [t.row(3), t.row(5)])
check("  the outline sits where Up lands (same column as below)", t.cell(4, 7).data == "l" and t.cell(4, 7).underscore)
t.key(UP)
check("Up again: inside at the outlined spot", t.cursor() == (4, 7), t.cursor())
t.close()

long = "word " * 14   # 3 rows at 29 wide
fresh("x", "Q:" + A, "y")
d = json.load(open("t/store.json")); [b.update(content=long.strip()) for b in d["blocks"] if b["id"] == "20261001T100000-ca00"]; json.dump(d, open("t/store.json", "w"))
t = Term(rows=14)
check("a longer quote: its box's sides run down beside every row", all(side(t.cell(y, 2)) for y in (4, 5, 6)) and t.inside(4).startswith("word") and t.cell(7, 2).data == "└" and t.cell(8, 0).data == "3", [t.row(y) for y in range(3, 9)])
t.key(END, DOWN)
check("  selected from above: only the top heavy", t.cell(3, 2).data == "┏" and t.cell(7, 2).data == "└")
t.key(DOWN, DOWN, DOWN, DOWN, DOWN, UP)
check("  from below: only the bottom", t.cell(7, 2).data == "┗" and t.cell(3, 2).data == "┌", [t.row(3), t.row(7)])
t.close()

fresh("x", "Q:" + B); t = Term(rows=14)
check("nested: a quote's own blocks boxed inside it, text faint, the quote red, sides right beside", t.cell(4, 3).data == "┌" and t.cell(4, 3).fg == FAINT and t.inside(5) == "beta" and t.cell(6, 3).data == "└" and t.cell(7, 3).data == "┌" and t.cell(7, 3).fg == SOFT and side(t.cell(7, 2)) and side(t.cell(8, 3)) and t.inside(8) == "alpha body" and t.cell(9, 3).data == "└" and t.cell(10, 2).data == "└", [t.row(y) for y in range(3, 11)])
t.key(DOWN, DOWN, DOWN)  # B selected, inside B (over beta's box top), A selected inside B
check("  the inner quote selected: its top heavy, both boxes bright", t.cell(7, 3).data == "┏" and t.cell(8, 3).bold and t.cell(5, 2).bold, t.row(7))
t.close()
fresh("x", "Q:" + A, "y"); t = F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=80, rows=14)
t.key(END, F.MENU)   # the cursor just past "x": row 1, column 7
check("the menu opens at the cursor: just below it, its left edge under it", t.cell(2, 7).data == "┌" and "⌃/" in t.row(3)[7:12], [t.row(2), t.row(3)])
check("  only as wide as what it lists", 30 < t.row(2).index("┐") - 7 + 1 < 58, t.row(2).index("┐") - 7 + 1)
t.key(F.ESC, F.DOWN, F.DOWN, F.DOWN, F.DOWN, F.END)
for _ in range(60): t.key("w")   # far right: it moves left just enough to fit
t.key(F.MENU)
row = next(y for y in range(14) if "┌" in t.row(y) and "⌃/" in t.row(y + 1))
check("  near the right edge it moves left just enough", t.row(row)[78] == "┐" and t.row(row).index("┌", 6) < t.cursor()[1], (t.row(row), t.cursor()))
t.close()
F.report("LOOK")
