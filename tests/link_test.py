import os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, LEFT, RIGHT, HOME, END, ESC, ENTER, BS, QUIT as Q, UNDO as Z, REDO as Y, MENU
S = F.use_store("t/link.json", clean=True)
HOST, CH, C2 = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002"
BOWL, CB = "20261001T100000-c000", "20261001T100000-c001"
SENT = "I went to the alley and the lanes were waxed."
def fresh():
    F.write_store([blk(HOST, [CH, C2], "host"), blk(CH, SENT), blk(C2, "next block"),
                   blk(BOWL, [CB], "Bowling"), blk(CB, "bowling notes")], [HOST, BOWL])
def B(): return S.index(S.load_data())
def undated(links): return [{k: v for k, v in l.items() if k != "created"} for l in links or []]   # (dates checked in backlink_test)
def ls(): return undated(B()[CH].get("links", []))
def bar(t): return t.row(t.scr.lines - 1)
SEL, CTRL_K, CTRL_SK, CTRL_O = "\x1b[1;2C", "\x0b", "\x1b[107;6u", "\x0f"
def link_alley(t, pick=("bowl", ENTER)):  # "alley" (14-19) -> Bowling
    t.key(UP, HOME, *[RIGHT] * 14, *[SEL] * 5, CTRL_K, *pick); t.settle()

fresh(); t = F.fw("host", rows=20)
t.key(UP, HOME, *[RIGHT] * 14, *[SEL] * 5, MENU)
check("with a selection the menu offers Link to an entry, ctrl+k", "Link to a pericope" in t.text() and "ctrl+k" in t.text(), t.text())
t.key(ESC, CTRL_K)
check("ctrl+k: the entry search, with + new entry", "link ›" in t.text() and "+ new pericope" in t.text(), t.text())
t.key("bowl", ENTER); t.settle()
same("picking one links the selection to it", ls(), [{"to": BOWL, "at": [14, 19]}])
check("  drawn with an ↗ after it", "alley↗ and" in t.text(), t.text())
t.key(LEFT)
check("  and the bar names where it points, with the cursor on it", "↗ Bowling" in bar(t), bar(t))
t.key(RIGHT)
check("  the cursor after it sits after the ↗", t.scr.cursor.x == t.row(t.scr.cursor.y).index("↗") + 1, (t.scr.cursor.x, t.row(t.scr.cursor.y)))
check("  the header doesn't show links", "links" not in t.row(1), t.row(1))
t.key(HOME, "XX"); t.settle()
same("typing before it moves it along", ls()[0]["at"], [16, 21])
t.key(*[RIGHT] * 19, "s"); t.settle()
check("typing right after it stays outside it", ls()[0]["at"] == [16, 21] and "alley↗s" in t.text(), (ls(), t.text()))
t.key(*[LEFT] * 3, "-"); t.settle()
same("typing inside it grows it", ls()[0]["at"], [16, 22])
t.key(Q, ESC); t.done()

fresh(); t = F.fw("host", rows=20)
link_alley(t)
t.key(CTRL_O)
check("ctrl+o on a link opens the entry it points to", "host ›" in bar(t) and "bowling notes" in t.text(), bar(t))
t.key(Q)
check("  ^Q comes back", "host ›" not in bar(t) and "alley↗" in t.text(), bar(t))
t.key(CTRL_SK); t.settle()
check("ctrl+shift+k removes the link; the text stays", ls() == [] and B()[CH]["content"] == SENT and "↗" not in t.text(), ls())
t.key(Z); t.settle()
same("  ^Z brings it back", ls(), [{"to": BOWL, "at": [14, 19]}])
t.key(Z); t.settle()
same("^Z again: the link was never made", ls(), [])
t.key(Y); t.settle()
same("  ^Y makes it again", len(ls()), 1)
t.key(*[SEL] * 0, HOME, *[RIGHT] * 14, *[SEL] * 5, BS); t.settle()
check("deleting the linked text empties the link (kept)", ls()[0]["at"][0] == ls()[0]["at"][1] and "↗" not in t.text(), ls())
t.key(Z); t.settle()
check("  ^Z: the text and the link are back", ls()[0]["at"] == [14, 19] and "alley↗" in t.text(), (ls(), t.text()))
t.key(Q, ESC); t.done()

fresh(); t = F.fw("host", rows=20)
link_alley(t, ("Lanes", UP, UP, ENTER))
new = next(r for r in S.entry_ids(S.load_data()) if r not in (HOST, BOWL))
check("+ new entry: an entry titled with what you typed, linked", B()[new]["title"] == "Lanes" and ls()[0]["to"] == new, (B()[new], ls()))
t.key(Q, ESC); t.done()
S.delete_entry(new)
same("deleting the entry it points to drops the link", ls(), [])

fresh(); t = F.fw("host", rows=20)
link_alley(t)
t.key(Q, ESC); t.done()
t = F.fw("host", rows=20)
check("reopened, the link is still drawn", "alley↗" in t.text(), t.text())
row = next(i for i in range(t.scr.lines) if "alley↗" in t.row(i))
x = t.row(row).index("↗") + 1
t.key("\x1b[M" + chr(32) + chr(33 + x) + chr(33 + row) + "\x1b[M" + chr(35) + chr(33 + x) + chr(33 + row), "Q"); t.settle()
check("a click just past the ↗ lands just after the link", "alley↗Q and" in t.text() and B()[CH]["content"].startswith("I went to the alleyQ"), t.text())
t.key(Q, ESC); t.done()
fresh(); t = F.fw("host", rows=20)
link_alley(t)
t.key(HOME, *[RIGHT] * 10, ENTER); t.settle()
second = S.children(B()[HOST])[1]
check("Enter before a link: the link goes with its text to the new block",
      ls() == [] and undated(B()[second].get("links")) == [{"to": BOWL, "at": [4, 9]}] and "alley↗" in t.text(), (ls(), B()[second].get("links")))
t.key(BS); t.settle()
same("  Backspace joining them back: it's back where it was", ls(), [{"to": BOWL, "at": [14, 19]}])
t.key(END, ENTER, "more"); t.settle()
same("  Enter after it leaves it be", ls(), [{"to": BOWL, "at": [14, 19]}])
t.key(Q, ESC); t.done()

QB = "20261001T100000-b003"
F.write_store([blk(HOST, [CH, QB, C2], "host"), blk(CH, SENT), blk(QB, {"quote": BOWL}), blk(C2, "next block"),
               blk(BOWL, [CB], "Bowling"), blk(CB, "bowling notes")], [HOST, BOWL])
t = F.fw("host", rows=24)
click = lambda x, y: "\x1b[M" + chr(32) + chr(33 + x) + chr(33 + y) + "\x1b[M" + chr(35) + chr(33 + x) + chr(33 + y)
t.key(click(6 + 14, 5), *[SEL] * 5, CTRL_K, "bowl", ENTER); t.settle()   # "alley", by a click before it
t.key(click(8, 8))   # into the quote's text
check("inside a quote, the entry's own links still show", "Bowling" in bar(t) and "bowling notes" in t.text() and "alley↗" in t.text(),
      (bar(t), t.text()))
t.key(Q, ESC); t.done()
check("no drafts left behind", not [x for x in os.listdir(F.DEV) if x.startswith(".fw-")], os.listdir(F.DEV))
F.report("LINK")
