import os, json, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, QUIT as Q, ESC, UP, DOWN
DEV = F.DEV
S = F.use_store("t/app.json", clean=True)
def Fw(*args): return F.fw(*args)
def entries():
    d = S.load_data(); B = S.index(d)
    return {S.display_title(B, e): S.own_text(B, e) for e in S.entry_ids(d)}

f = Fw()
f.key("first thought"); f.key(Q)
check("fw: write, ^Q goes home (not the shell)", "open ›" in f.text() and "+ new pericope" in f.text() and "first thought" in f.text(), f.text().splitlines()[:4])
check("  home says it saved", "saved · first thought" in f.text())
f.key("\r"); f.key("\r", "more"); f.key(Q)   # opened at the end of its text: Enter, a new block
check("Enter opens the entry just closed (selected by default), at the end of its text", entries().get("first thought", "") == "first thought\nmore", entries())
f.key(UP + "\r"); f.key("second one"); f.key(Q)
check("+ new entry starts another", "second one" in entries(), list(entries()))
f.key("first"); f.key("\r"); f.key("!"); f.key(Q)
check("typing filters; Enter opens the match, typing goes on from the end", entries()["first thought"].endswith("more!"), entries()["first thought"])
check("  back home: the search as it was left", "open › first" in f.text(), f.text().splitlines()[:4])
f.key("\x7f" * 5)
f.key("garden notes"); f.key("\r"); f.key("tulips"); f.key(Q)
d = S.load_data(); B = S.index(d)
check("no match: Enter makes a new entry with that title", any(B[e]["title"] == "garden notes" and S.own_text(B, e) == "tulips" for e in S.entry_ids(d)))
f.key("\x7f" * 13, UP * 5 + "\r"); f.key(Q)   # (the search emptied, then left: the garden, its first card + new)
check("an empty new entry is discarded, and home says so", "discarded" in f.text() and len(entries()) == 3, f.text().splitlines()[-1])
f.key("thought")
check("searching home filters by title", "first thought" in f.text() and "second one" not in f.text(), f.text().splitlines()[:6])
f.key("\x7f" * 7 + ESC)
check("Esc on home quits fw", f.done())
check("  leaving no drafts behind", not [x for x in os.listdir(DEV) if x.startswith(".fw-")], [x for x in os.listdir(DEV) if x.startswith(".fw-")])
g = Fw("open"); check("fw open starts at home", "open ›" in g.text()); g.key(ESC); check("  and Esc quits", g.done())
h = Fw("garden notes"); h.key(" and roses"); h.key(Q)
check("fw <title> opens that entry, then home", "open ›" in h.text() and entries()["garden notes"].endswith("and roses"), entries()["garden notes"])
h.key(Q); check("^Q on home quits too", h.done())
F.report("APP")
