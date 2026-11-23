# the header (no id, dates pretty) and a quote's top line (which properties it shows)
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, DOWN, MENU, UNDO as Z
S = F.use_store("t/store.json")
A, CA, B, CB, QBA = "20261001T100000-aa00", "20261001T100000-aa01", "20261002T100000-bb00", "20261002T100000-bb01", "20261002T100000-bb02"
ME, X, Q = "20261021T230000-ff00", "20261021T230000-ff01", "20261021T230000-ff02"
def fresh(target=A, inner_show=None):
    qba = {"quote": A, **({"show": inner_show} if inner_show else {})}
    F.write_store([blk(A, [CA], "Alpha", created="2026-10-21T15:04:00-04:00", words=2), blk(CA, "alpha body"),
                   blk(B, [CB, QBA], "Beta"), blk(CB, "beta"), blk(QBA, qba),
                   blk(ME, [X, Q], "mine"), blk(X, "my text"), blk(Q, {"quote": target})], [A, B, ME])
    F.write_meta(ME, fields=[{"key": "id", "value": ME, "editable": False},
                             {"key": "created", "value": "2026-10-21T23:00:00-04:00", "editable": False},
                             {"key": "title", "value": "mine", "editable": True}])
    open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), ME))
def Term(): return F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=50, rows=16)
def show(qid=Q): return S.index(S.load_data())[qid]["content"].get("show")
def top(): return next(y for y in range(t.scr.lines) if t.row(y).startswith("2 "))   # the quote's top line: block 2's

check("pretty_time: a date and a clock", S.pretty_time("2026-10-21T00:05:00-04:00") == "Oct 21, 2026, 12:05 am", S.pretty_time("2026-10-21T00:05:00-04:00"))
check("  or just the date", S.pretty_time("2026-10-21T15:04:00-04:00", clock=False) == "Oct 21, 2026")
b = {"content": {"quote": A, "show": ["title"]}}; b = S.with_mask(b, [0, 3])
check("a new mask keeps what the quote shows", b["content"] == {"quote": A, "show": ["title"], "mask": [0, 3]}, b)
b = S.with_show(b, ["words", "title"]); check("  and show keeps the mask, in a fixed order", b["content"] == {"quote": A, "mask": [0, 3], "show": ["title", "words"]}, b)
b = S.with_show(b, []); check("  none: no show at all", "show" not in b["content"], b)
schema = S.load_schema()
check("the schema takes a show list", not S.validate_instance(blk(Q, {"quote": A, "show": ["title", "created"]}), schema))
check("  of known properties only", S.validate_instance(blk(Q, {"quote": A, "show": ["colour"]}), schema))
F.write_store([blk(A, "x", "Alpha")], [A], version=5)
check("a v5 store reads as the current version", S.load_data()["schemaVersion"] == S.SCHEMA_VERSION)

fresh(); t = Term()
check("the header leaves the id out", ME not in t.row(1) and "id" not in t.row(1).split(), t.row(1))
check("  and writes the date as people do", "created Oct 21, 2026, 11:00 pm" in t.row(1), t.row(1))
check("a quote's top line is plain to start", t.row(top()).startswith("2 ┌───"), t.row(top()))
t.key(DOWN, MENU)
check("Ctrl+/ on a quote: its top line is one entry, a submenu", "Its top line…" in t.text() and "Show its title" not in t.text(), t.text())
t.key("date")
check("  but a search finds what's inside it", "Show its date" in t.text() and "Its top line" not in t.text(), t.text())
t.key("\r"); t.settle()
check("  showing its date: in its top line, and stored on the quote", " Oct 21, 2026 " in t.row(top()) and "Alpha" not in t.row(top()) and show() == ["created"], (t.row(top()), show()))
check("  and the menu stays open, the label turned to Hide", "Hide its date" in t.text(), t.text())
t.key(F.BS, F.BS, F.BS, F.BS, "title", "\r"); t.settle()
check("  then its title: title first, whatever order they're picked in", " Alpha · Oct 21, 2026 " in t.row(top()) and show() == ["title", "created"], (t.row(top()), show()))
t.key(F.ESC)
check("Esc after a toggle closes it, typing nothing", "Hide its" not in t.text() and "title" not in t.inside(top() + 1) and t.inside(top() + 1) == "alpha body", t.text())
t.key(MENU, "top", "\r")
check("the submenu: its toggles, as they are now", "Hide its title" in t.text() and "Hide its date" in t.text() and "Show its word count" in t.text() and "Its top line ›" in t.text(), t.text())
t.key("date", "\r"); t.settle()
check("  hiding one", " Alpha ─" in t.row(top()) and show() == ["title"], (t.row(top()), show()))
t.key(F.BS, F.BS, F.BS, F.BS, F.BS)
check("  Backspace past the query: back to the top level", "Its top line…" in t.text() and "Open it" in t.text(), t.text())
t.key(F.ESC, Z); t.settle()
check("^Z undoes it, store and all", "━ Alpha · Oct 21, 2026 ━" in t.row(top()) and show() == ["title", "created"], (t.row(top()), show()))
t.key(DOWN, MENU, "word", "\r", F.ESC); t.settle()
check("inside the quote, the menu works on the quote it's in", show() == ["title", "created", "words"] and "─ Alpha · Oct 21, 2026 · 2 words ─" in t.row(top()), (t.row(top()), show()))
t.close()

fresh(B, ["title"]); t = Term()
check("a quote inside a quote shows its own top line", any("│┌─ Alpha ─" in t.row(y) for y in range(t.scr.lines)), t.text())
t.close()
F.report("QHEAD")
