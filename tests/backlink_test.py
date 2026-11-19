# backlinks: the blocks pointing at a block itself (quotes, masked or not; links, dated), in the header; Enter lists them, opens one
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, DOWN, ENTER, ESC, QUIT as Q
S = F.use_store("t/backlink.json", clean=True)
T, T1, T2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
P1, Q1 = "20261002T100000-b000", "20261002T100000-b001"
P2, Q2 = "20261003T100000-c000", "20261003T100000-c001"
P3, L3 = "20261004T100000-d000", "20261004T100000-d001"
LOOSE = "20261005T100000-e000"
def B(): return S.index(S.load_data())
F.write_store([blk(T, [T1, T2], "target"), blk(T1, "first part"), blk(T2, "second part"),
               blk(P1, [Q1], "plain quoter", created="2026-10-02T10:00:00-04:00"), blk(Q1, {"quote": T}, created="2026-10-02T10:00:00-04:00"),
               blk(P2, [Q2], "masked quoter", created="2026-10-03T10:00:00-04:00"), blk(Q2, {"quote": T}, created="2026-10-03T10:00:00-04:00"),
               blk(P3, [L3], "linker"), {**blk(L3, "see the target here"), "links": [{"to": T, "at": [8, 14]}]},
               blk(LOOSE, {"quote": T})],
              [T, P1, P2, P3], version=9)
S.cmd_migrate(None)
S.mask_quote_to(Q2, T2)   # (masked to "second part")
same("the store moves to the current schema (links can carry a date since v13)", S.load_data()["schemaVersion"], S.SCHEMA_VERSION)
found = S.backlinks(B(), T)
same("backlinks of the target: each quote of it, masked or not, and the link; oldest first, the undated link first",
     [(x["kind"], x["home"]) for x in found], [("link", P3), ("quote", P1), ("masked quote", P2)])
same("  a masked quote of it points at it, not at the block it shows", S.backlinks(B(), T2), [])
check("  a quote no entry reaches isn't one", all(x["by"] != LOOSE for x in found))
same("  summed up", S.backlink_summary(found), "3 · 1 quote, 1 masked quote, 1 link")
S.link_text(L3, "see the target here", [0, 3], P1)
check("a link made now carries its date", all(l.get("created") for l in B()[L3]["links"] if l["to"] == P1), B()[L3]["links"])

t = F.fw("target", rows=30)
check("the header shows them", "backlinks" in t.text() and "3 · 1 quote, 1 masked quote, 1 link" in t.text(), t.text())
t.key(UP, UP)   # (the end of "second part") up into the title, up again to kinds, and to backlinks
t.key(UP, UP)
t.key(ENTER)
check("Enter on it lists them: kind, where, when", "link in linker" in t.text() and "quote in plain quoter" in t.text()
      and "masked quote in masked quoter" in t.text() and "undated" in t.text(), t.text())
t.key(DOWN, ENTER)
check("Enter on one opens its entry, on the trail back here", t.until(lambda: "target ›" in t.text()) and "plain quoter" in t.text(), t.text())
t.key(Q); t.settle()
check("  ^Q comes back", "first part" in t.text() and "›" not in t.row(t.scr.lines - 1), t.row(t.scr.lines - 1))
t.key(Q, ESC); t.done()
# the line shows only while something points at it (the user, 2026-11-17)
t = F.fw("linker", rows=30)
check("  (open)", t.until(lambda: "target↗ here" in t.text()), t.text())
check("a pericope nothing points at: no backlinks line", "backlinks" not in t.text(), t.text())
qd = S.index(S.load_data())
def quote_linker(data, blocks):
    i = S.new_id(blocks); S.add_block(data, blocks, i, {"quote": P3}); blocks[P1]["content"].append(i)
S.transact(quote_linker)
check("  quoted elsewhere: the line comes, by itself", t.until(lambda: "backlinks" in t.text() and "1 quote" in t.text()), t.text())
t.key(Q, ESC); t.done()

F.report("BACKLINK")
