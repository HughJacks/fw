# `updated` on every block, kept by the store; and what's on screen follows it live
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, blk, DOWN, END, MENU, UNDO as Z
S = F.use_store("t/store.json")
A, CA, CA2, B, CB, QBA, C, CC, QCA = ("20261001T100000-aa00", "20261001T100000-aa01", "20261001T100000-aa02",
    "20261002T100000-bb00", "20261002T100000-bb01", "20261002T100000-bb02",
    "20261003T100000-cc00", "20261003T100000-cc01", "20261003T100000-cc02")
OLD = "2026-10-01T10:00:00-04:00"
def fresh():
    F.write_store([blk(A, [CA, CA2], "Alpha"), blk(CA, "alpha body"), blk(CA2, "second"),
                   blk(B, [CB, QBA], "Beta"), blk(CB, "beta"), blk(QBA, {"quote": A}),
                   blk(C, [CC, QCA], "Gamma"), blk(CC, "gamma"), blk(QCA, {"quote": A, "mask": [0, 5]})], [A, B, C])
    S.cmd_migrate(None)
def up(i): return S.index(S.load_data())[i].get("updated")

fresh()
check("a store from before: every block's updated starts as when it was made", all(b.get("updated") == b.get("created") for b in S.load_data()["blocks"]))
draft = S.block_draft(S.index(S.load_data()), A)
S.commit(A, draft.replace("alpha body", "alpha body, edited"), [])
check("editing a block's text: that block was updated now", up(CA) != OLD, up(CA))
check("  and so was the entry it's part of", up(A) != OLD and up(A) == up(CA), (up(A), up(CA)))
check("  not its sibling", up(CA2) == OLD)
check("  not the entries quoting it (their words do follow)", up(B) == OLD and up(QBA) == OLD and S.index(S.load_data())[B]["words"] == 5, (up(B), S.index(S.load_data())[B]["words"]))
check("  nor a masked quote whose anchors only moved along", up(QCA) == OLD and up(C) == OLD, (up(QCA), up(C)))
h, record = S.set_quote_show(QBA, ["title"])
check("showing a quote's title updates the quote", up(QBA) != OLD)
S.restore(record)
check("  ^Z puts back the time it had", up(QBA) == OLD, up(QBA))
check("the schema knows it: readOnly, a date-time", S.load_schema()["properties"]["updated"]["readOnly"] is True)

fresh()
S.commit(A, S.block_draft(S.index(S.load_data()), A), [])   # nothing changed (a stamp, if any, is this second)
F.write_meta(B, fields=[{"key": "updated", "value": OLD, "editable": False}, {"key": "title", "value": "Beta", "editable": True}])
open("t/f.txt", "w").write(S.block_draft(S.index(S.load_data()), B))
t = F.editor("t/f.txt", "--meta", "t/f.meta.json", cols=60, rows=14)
check("the header shows when it was updated, pretty", "updated Oct 1, 2026, 10:00 am" in t.row(1), t.row(1))
t.key(END, "!"); t.settle()
check("  live: typing updates it at once", "updated Oct 1, 2026" not in t.row(1) and up(B) != OLD, (t.row(1), up(B)))
check("no [+], no ^S: nothing to save", "[+]" not in t.text())
t.key(DOWN, MENU, "word", "\r", F.ESC); t.settle()   # the menu stays open after a toggle
before = t.text()
t.key(DOWN, END, " two more"); t.settle()   # inside the quote of Alpha: its text grows
row = next((l for l in t.scr.display if "words" in l and "┌" in l), "")
check("a quote's word count follows typing inside it, live", "words" in row and row != next((l for l in before.split("\n") if "words" in l and "┌" in l), ""), row)
t.close()
F.report("UPDATED")
