# deleting the entry that's open: for good; a quote of it keeps its last text (a quote is a pointer)
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, UP, DOWN, ESC, MENU, QUIT as Q
S = F.use_store("t/store.json")
A, CA, ME, X, QA = "20261001T100000-aa00", "20261001T100000-aa01", "20261021T230000-ff00", "20261021T230000-ff01", "20261021T230000-ff02"
def fresh(mask=None):
    F.write_store([blk(A, [CA], "Alpha"), blk(CA, "alpha body, all of it"),
                   blk(ME, [X, QA], "mine"), blk(X, "x"), blk(QA, {"quote": A, **({"mask": mask} if mask else {})})], [A, ME])
    S.cmd_migrate(None)
def B(): return S.index(S.load_data())

fresh()
d = S.block_draft(B(), A); i = d.index("body")
fresh([i, i + 4])
kept = S.delete_entry(A)
check("deleting an entry: gone from the list, its blocks erased", A not in S.entry_ids(S.load_data()) and A not in B() and CA not in B())
check("  a quote of it keeps the last of what it showed, as plain text", B()[QA]["content"] == "…body…" and kept == 1, (B()[QA]["content"], kept))

fresh(); f = F.fw("Alpha")
f.key(MENU)
check("the menu has no Delete this entry: deleting is the window's", "Delete this pericope" not in f.text() and "Delete this entry" not in f.text(), f.text())
f.key(ESC, "\x04")
check("Ctrl+D in the editor asks first", "delete 'Alpha'?" in f.text(), f.row(15))
f.key("n")
check("  any key but y keeps it", A in S.entry_ids(S.load_data()) and "kept" in f.text(), f.row(15))
f.key("\x04", "y")
check("  y deletes it, and fw goes home, saying so", A not in S.entry_ids(S.load_data()) and "open ›" in f.text() and "deleted 'Alpha'" in f.text() and "1 quote of it now plain text" in f.text(), f.text())
check("  the quote in my entry is plain text now", B()[QA]["content"] == "alpha body, all of it", B()[QA]["content"])
f.key(ESC); f.done()
check("no drafts left behind", not [x for x in __import__("os").listdir(F.DEV) if x.startswith(".fw-")])

fresh(); f = F.fw("mine")
f.key(UP, MENU, "open", "\r")   # Open it: into Alpha
f.key("\x04", "y")
check("deleted after Open it: back where Open it was, the quote now its text", "mine" in f.text() and "alpha body, all of it" in f.text() and "Alpha ›" not in f.row(15) and A not in S.entry_ids(S.load_data()), f.text())
f.key(Q, ESC); f.done()
fresh(); f = F.fw("open")
f.key("alpha")
f.key("\x04")   # Ctrl+D on home: the entry selected
check("home: Ctrl+D asks before deleting the entry selected", "delete 'Alpha'?" in f.text(), f.text())
f.key("n")
check("  any key but y keeps it", A in S.entry_ids(S.load_data()) and "kept" in f.text(), f.text())
f.key("alpha", "\x04", "y")
check("  y deletes it: gone from the list, its quote plain text", A not in S.entry_ids(S.load_data()) and "deleted 'Alpha'" in f.text() and B()[QA]["content"] == "alpha body, all of it", f.text())
f.key(UP, "\x04")   # up on "+ new entry": nothing to delete
check("  on the new-entry row it does nothing", "delete '" not in f.text(), f.text())
f.key(ESC); f.done()
F.report("DELETE")
