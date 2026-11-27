# links (a span of a block of text pointing at a pericope, moved along with every edit of its text) and backlinks
# (what points at a block: quotes of it, masked or not, links to it, kinds, paraphrases)
import sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("link")
HOST, CH, C2, BOWL, CB = ("20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002",
                          "20261001T100000-c000", "20261001T100000-c001")
SENT = "I went to the alley and the lanes were waxed."
def fresh():
    F.store(blk(HOST, [CH, C2], "host", entry=True), blk(CH, SENT), blk(C2, "next block"),
            blk(BOWL, [CB], "Bowling", entry=True), blk(CB, "bowling notes"))
def ls(i=CH): return [{k: v for k, v in l.items() if k != "created"} for l in F.blocks()[i].get("links", [])]
def write(text):   # the host's first block's text, as an editor saves it
    S.commit(HOST, S.block_draft(F.blocks(), HOST).replace(F.content(CH), text, 1), [])

fresh()
_, record = S.link_text(CH, SENT, [14, 19], BOWL)
same("a span linked to a pericope", ls(), [{"to": BOWL, "at": [14, 19]}])
check("  dated", all(l.get("created") for l in F.blocks()[CH]["links"]))
write("XX" + SENT)
same("typing before it moves it along", ls()[0]["at"], [16, 21])
write("XXI went to the alleys and the lanes were waxed.")
same("typing right after it stays outside it", ls()[0]["at"], [16, 21])
write("XXI went to the al-leys and the lanes were waxed.")
same("typing inside it grows it", ls()[0]["at"], [16, 22])
fresh(); S.link_text(CH, SENT, [14, 19], BOWL)
d = S.block_draft(F.blocks(), HOST)
S.commit(HOST, d.replace("I went ", "I went \n{{block}}\n"), [])
second = S.children(F.blocks()[HOST])[1]
same("a block split before it: the link goes with its text to the new block", (ls(), ls(second)), ([], [{"to": BOWL, "at": [7, 12]}]))
S.commit(HOST, d, [])
same("  joined back: where it was", ls(), [{"to": BOWL, "at": [14, 19]}])
write(SENT.replace("alley", ""))
check("its text deleted: the link kept, empty", ls()[0]["at"][0] == ls()[0]["at"][1], ls())
fresh(); S.link_text(CH, SENT, [14, 19], BOWL)
record = S.unlink_text(CH, BOWL, [14, 19])
check("unlinked: the link gone, the text stays", ls() == [] and F.content(CH) == SENT)
S.restore(record)
same("  undone: back", ls(), [{"to": BOWL, "at": [14, 19]}])
new, record = S.link_text(CH, SENT, [26, 31], None, "Lanes")
same("to a new pericope: one titled so, linked", (F.blocks()[new]["title"], F.blocks()[new].get("entry"), ls()[-1]["to"]), ("Lanes", True, new))
S.restore(record)
check("  undone: the link and the pericope gone", new not in F.blocks() and len(ls()) == 1)
check("only text can be linked; only to a pericope", F.refused(S.link_text, HOST, "", [0, 1], BOWL) and F.refused(S.link_text, CH, SENT, [0, 1], CB))
record = S.add_links(C2, "next block", [{"to": BOWL, "at": [0, 4]}, {"to": "20261001T100000-ffff", "at": [5, 10]}])
same("links pasted with their text: kept, but not to a pericope that's gone", ls(C2), [{"to": BOWL, "at": [0, 4]}])
S.delete_entry(BOWL)
same("deleting the pericope it points to drops the link", (ls(), ls(C2)), ([], []))

# --- backlinks
T, T1, T2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
P1, Q1, P2, Q2, P3, L3, LOOSE = ("20261002T100000-b000", "20261002T100000-b001", "20261003T100000-c000", "20261003T100000-c001",
                                 "20261004T100000-d000", "20261004T100000-d001", "20261005T100000-e000")
F.store(blk(T, [T1, T2], "target", entry=True), blk(T1, "first part"), blk(T2, "second part"),
        blk(P1, [Q1], "plain quoter", entry=True, created="2026-10-02T10:00:00-04:00"), blk(Q1, {"quote": T}, created="2026-10-02T10:00:00-04:00"),
        blk(P2, [Q2], "masked quoter", entry=True, created="2026-10-03T10:00:00-04:00"), blk(Q2, {"quote": T}, created="2026-10-03T10:00:00-04:00"),
        blk(P3, [L3], "linker", entry=True), {**blk(L3, "see the target here"), "links": [{"to": T, "at": [8, 14]}]},
        blk(LOOSE, {"quote": T}), version=9)
S.mask_quote_to(Q2, T2)
same("the store at the current schema (links dated since v13)", S.load_data()["schemaVersion"], S.SCHEMA_VERSION)
found = S.backlinks(F.blocks(), T)
same("backlinks: each quote of it, masked or not, and the link; oldest first, the undated link first",
     [(x["kind"], x["home"]) for x in found], [("link", P3), ("quote", P1), ("masked quote", P2)])
same("  a masked quote of it points at it, not at the block it shows", S.backlinks(F.blocks(), T2), [])
check("  a quote no entry reaches isn't one", all(x["by"] != LOOSE for x in found))
same("  summed up", S.backlink_summary(found), "3 · 1 quote, 1 masked quote, 1 link")
same("  nothing pointing: none", S.backlinks(F.blocks(), P3), [])
F.report()
