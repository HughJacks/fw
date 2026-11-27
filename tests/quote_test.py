# quotes: a live view of another block. Turned into one (pop out, nested from a selection), into text (detach),
# a top line (show), locked; each change a record that restore undoes completely, store and all
import copy, json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("quote")
A, CA, CB, ME, T, QM = ("20261001T100000-aaaa", "20261001T100000-c0a0", "20261001T100000-c0b0",
                        "20261021T230000-0000", "20261021T230000-c001", "20261021T230000-9999")
def fresh(mask=None, **q):
    F.store(blk(A, [CA, CB], "Alpha", entry=True, created="2026-10-21T15:04:00-04:00"), blk(CA, "the quick brown fox"),
            blk(CB, "jumps over the lazy dog"), blk(ME, [T, QM], "mine", entry=True), blk(T, "x"),
            blk(QM, {"quote": A, **({"mask": mask} if mask else {}), **q}), version=9)
fresh(); d = S.block_draft(F.blocks(), A); QB = [d.index("quick"), d.index("brown") + 5]
def undone(label, do, *args):
    """`do(*args)` changes the store; its record (wherever it comes back) puts the store back as it was, and back again."""
    before = F.state()
    out = do(*args)
    record = next(x for x in (out if isinstance(out, tuple) else (out,))[::-1] if isinstance(x, dict) and "blocks" in x)
    after = F.state()
    redo = S.restore(record)
    check(f"{label}, undone: as if it never happened", F.state() == before and after != before)
    S.restore(redo)
    check("  and redone", F.state() == after)
    return out

fresh()
entry = undone("pop out (Turn into a quote)", S.pop_out, T)[0]
b = F.blocks()
same("  the block now quotes a new entry, which holds its text, titled from it", (S.quoted(b[T])[0], S.own_text(b, entry), S.display_title(b, entry)), (entry, "x", "x"))
check("  a quote can't be popped out again", F.refused(S.pop_out, T))
fresh(QB)
text = undone("detach (Turn into text)", S.detach, QM)[0]
same("  a plain copy of what it showed, … for what was hidden", (text, F.content(QM)), ("…quick brown…", "…quick brown…"))
fresh(QB)
undone("Remove mask", S.set_quote_mask, QM, None, None)
same("  shows all", S.quoted(F.blocks()[QM])[1], None)
fresh()
undone("mask to a block", S.mask_quote_to, QM, CB)
same("  it shows just that block", S.shown_text(F.blocks(), QM), "…\njumps over the lazy dog")
check("  a block outside what it quotes: refused", F.refused(S.mask_quote_to, QM, T))

# --- a new pericope, quoted (the quote search's + new pericope)
fresh()
new, record = S.new_entry("groceries", ME)
F.edit(lambda d, b: (S.add_block(d, b, "20261021T230000-0a00", {"quote": new}), b[ME]["content"].append("20261021T230000-0a00")))
S.commit(new, "milk", [])
same("+ new pericope: an entry titled so, quoted here, written in", (F.kids(ME)[-1], S.own_text(F.blocks(), new)), (("quote", new), "milk"))
S.restore(record)
check("  its record takes back the quote and the entry", new not in F.blocks() and F.kids(ME) == ["x", ("quote", A)], F.kids(ME))

# --- its top line: which of its source's properties it shows
same("pretty_time: a date and a clock", S.pretty_time("2026-10-21T00:05:00-04:00"), "Oct 21, 2026, 12:05 am")
same("  or just the date", S.pretty_time("2026-10-21T15:04:00-04:00", clock=False), "Oct 21, 2026")
b = S.with_mask({"content": {"quote": A, "show": ["title"]}}, [0, 3])
same("a new mask keeps what the quote shows", b["content"], {"quote": A, "show": ["title"], "mask": [0, 3]})
b = S.with_show(b, ["words", "title"])
same("  and show keeps the mask, in a fixed order", b["content"], {"quote": A, "mask": [0, 3], "show": ["title", "words"]})
check("  none: no show at all", "show" not in S.with_show(b, [])["content"])
schema = S.load_schema()
check("the schema takes a show list of known properties only", not S.validate_instance(blk(QM, {"quote": A, "show": ["title", "created"]}), schema)
      and S.validate_instance(blk(QM, {"quote": A, "show": ["colour"]}), schema))
fresh()
undone("show its title and date", S.set_quote_show, QM, ["created", "title"])
same("  stored on the quote, title first", S.quote_show(F.blocks()[QM]), ["title", "created"])

# --- locked (schema v17): nothing written through it, nor anything shown through it
from fw import migrate as M
QL, QN, DEEP = "20261001T100000-e001", "20261001T100000-e002", "20261001T100000-b000"
d = json.load(open(S.DATA_PATH))
up = M.upgrade(copy.deepcopy({**d, "schemaVersion": 16}), now=S.now_local(), new_id=S.new_id)
check("v16 → v17: marked to be saved, the blocks as they were", M.behind({**d, "schemaVersion": 16}) and up["blocks"] == d["blocks"])
check("the schema takes lock: true on a quote, only true", not S.validate_instance(blk(QL, {"quote": A, "lock": True}), schema)
      and S.validate_instance(blk(QL, {"quote": A, "lock": False}), schema))
b = S.with_lock({"content": {"quote": A, "show": ["title"]}}, True)
same("with_lock keeps the rest of the quote", b["content"], {"quote": A, "show": ["title"], "lock": True})
same("  unlocking leaves no lock", S.with_lock(b, False)["content"], {"quote": A, "show": ["title"]})
lib = {QL: {"content": {"quote": A, "lock": True}}, QM: {"content": {"quote": A}}, QN: {"content": {"quote": DEEP}}}
same("locked_by: nothing open, writable", S.locked_by(lib, []), None)
same("  inside an unlocked quote, writable", S.locked_by(lib, [QM]), None)
same("  inside a locked one, locked by it", S.locked_by(lib, [QL]), QL)
same("  a quote inside a locked one: locked by the outer (the cascade)", S.locked_by(lib, [QL, QN]), QL)
same("  a locked one inside an unlocked one: locked by the inner", S.locked_by(lib, [QM, QL]), QL)
fresh()
undone("lock it", S.set_quote_lock, QM, True)
check("  stored on the quote", S.quote_lock(F.blocks()[QM]))

# --- a selection turned into a quote, nested where it was (nest_out)
HOST, CH, C2 = "20261001T100000-b100", "20261001T100000-b101", "20261001T100000-b102"
G = "20261001T100000-b103"
SENT = "I went to the alley and the lanes were waxed so we bowled late."
def nest_fresh():
    F.store(blk(HOST, [CH, C2], "host", entry=True), {**blk(CH, SENT), "links": [{"to": G, "at": [14, 19]}]}, blk(C2, "next block"),
            blk(G, "g", "g", entry=True))
nest_fresh()
new = undone("a selection turned into a quote", S.nest_out, CH, "I went to the alley and ", "the lanes were waxed", " so we bowled late.")[0]
same("  the block holds its text before, the quote, its text after", F.kids(CH), ["I went to the alley and ", ("quote", new), " so we bowled late."])
same("  the new entry holds the selection", S.own_text(F.blocks(), new), "the lanes were waxed")
same("  the link went with its text", [F.blocks()[k].get("links", [{}])[0].get("at") for k in S.children(F.blocks()[CH])[:1]], [[14, 19]])
same("  words count the quoted text once", F.blocks()[HOST]["words"], len((SENT + " next block").split()))
first = S.children(F.blocks()[CH])[0]
S.nest_out(first, "", "I went", " to the alley and")
same("a selection in a container's child splits it there, not a level deeper", [type(c).__name__ for c in F.kids(CH)], ["tuple", "str", "tuple", "str"])

# --- cut blocks: kept while the clipboard holds them (to be moved by a paste), erased once it holds something else;
fresh()
S.save_clip({"text": "jumps over the lazy dog", "cut": True, "blocks": [{"id": CB}]})
S.commit(A, f"{S.block_line(CA)}\nthe quick brown fox", [])
check("a block cut: gone from its entry, but kept", CB in F.blocks() and F.kids(A) == ["the quick brown fox"], F.kids(A))
same("  the clip says so", S.clip_holds(), [CB])
S.save_clip(None)
S.cmd_migrate(None)
check("  something else copied: it goes", CB not in F.blocks())
F.report()
