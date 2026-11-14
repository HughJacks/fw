import json, os, sys
sys.path.insert(0, "."); import drive, fwtest as F
from fwtest import same as check
os.environ["FW_DATA"] = os.path.abspath("t/store.json")
META = os.path.abspath("t/f.meta.json")
def meta(title=""):
    json.dump({"id": "X", "fields": [{"key": "id", "value": "20261021T000000-abcd", "editable": False},
                                     {"key": "title", "value": title, "editable": True}]}, open(META, "w"))
def title(): return json.load(open(META))["fields"][1]["value"]
UP, DOWN, BS, LEFT, HOME = "\x1b[A", "\x1b[B", "\x7f", "\x1b[D", "\x1b[H"
body = "Notes on bowling alleys\nmore text"
meta(); drive.run(body, [UP, "!", DOWN, "\x11"], ["--meta", META], cols=50)
check("a derived title is editable in place (append)", title(), "Notes on bowling alleys!")
meta(); drive.run(body, [UP, BS * 7, DOWN, "\x11"], ["--meta", META], cols=50)
check("  (shorten)", title(), "Notes on bowling")
meta(); drive.run(body, [UP, HOME, "My ", DOWN, "\x11"], ["--meta", META], cols=50)
check("  (insert at the start)", title(), "My Notes on bowling alleys")
meta(); drive.run(body, [UP, DOWN, "x", "\x11"], ["--meta", META], cols=50)
check("visiting without changing it leaves it derived", title(), "")
meta(); drive.run(body, [UP, BS * 30, DOWN, "\x11"], ["--meta", META], cols=50)
check("deleting it all goes back to derived", title(), "")
meta("Written"); drive.run(body, [UP, " one", DOWN, "\x11"], ["--meta", META], cols=50)
check("a written title edits as before", title(), "Written one")
meta(); drive.run(body, [UP, BS * 30, "Bowling", DOWN, "\x11"], ["--meta", META], cols=50)
check("deleting it all, then typing: only what's typed (nothing derived mixed in)", title(), "Bowling")
meta(); drive.run(body, [UP, "\x01", "Fresh", DOWN, "\x11"], ["--meta", META], cols=50)
check("^A selects the whole field: typing replaces it", title(), "Fresh")
meta("Written"); drive.run(body, [UP, "\x01", BS, DOWN, "\x11"], ["--meta", META], cols=50)
check("  ^A then Backspace empties it (derived again, once you leave)", title(), "")
meta("Written"); drive.run(body, [UP, "\x01", LEFT, "!", DOWN, "\x11"], ["--meta", META], cols=50)
check("  a move drops the selection", title(), "Writte!n")

meta(); open("t/f.txt", "w").write(body)
t = F.editor("t/f.txt", "--meta", META, cols=50)
F.check("the header's box has an H in the gutter, as a block's number", F.re.match(r"\s*H ┌", t.row(0)) is not None, t.row(0))
t.key(UP, BS * 30)
F.check("emptied, the field stays empty while you're in it", "Notes on bowling" not in t.row(3), t.row(3))
t.key(DOWN)
F.check("  and shows the derived title once you leave", "Notes on bowling alleys" in t.row(3), t.row(3))
t.key("\x11"); t.done()
F.report("TITLE")
