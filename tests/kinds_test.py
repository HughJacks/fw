# kinds (shown as tags): what a pericope is (a poem, a to-do). A kind is a block, content {kind, blocks}: a name and a
# description of child blocks, a pericope of its own; a pericope carries the user's answers, kinds: {kind id: bool}.
# A model's guesses (kind-guesses.json beside the store) count from 0.9 (applied) and are maybes to review from 0.5;
# a model may propose a kind (kind-proposals.json), dismissed into kind-dismissed.json.
import copy, json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same
S = F.use_store("kinds")
from fw import migrate as M
from fw.search import Search, blocks_inside

MINE, M1, M2 = "20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002"
OTHER, O1 = "20261002T100000-b000", "20261002T100000-b001"
HOST, H1 = "20261003T100000-c000", "20261003T100000-c001"
POEM, PD = "20261004T100000-d000", "20261004T100000-d001"   # a kind, and a block of its description
T = F.T
blk = F.blk
def fresh(kinds=True):
    """mine: two blocks of text (mine a poem, when `kinds`); other: one; host: one; and the kind poem, described."""
    blocks = [blk(MINE, [M1, M2], "mine", True), blk(M1, "roses are red\nviolets are blue"), blk(M2, "buy milk"),
              blk(OTHER, [O1], "other", True), blk(O1, "an old pond"),
              blk(HOST, [H1], "host", True), blk(H1, "host text")]
    if kinds:
        blocks += [blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True), blk(PD, "a short piece in lines")]
        blocks[0]["kinds"] = {POEM: True}
    F.store(*blocks, version=16)
def B(): return F.blocks()

# --- the shape: migration and schema ---------------------------------------------------------------------
fresh(kinds=False)
d = json.load(open(os.environ["FW_DATA"]))
v15 = {**d, "schemaVersion": 15}
up = M.upgrade(copy.deepcopy(v15), now=S.now_local(), new_id=S.new_id)
check("v15 → v16 (and on): marked to be saved, the blocks as they were (no kinds yet)",
      M.SCHEMA_VERSION >= 16 and up["schemaVersion"] == M.SCHEMA_VERSION and M.behind(v15) and up["blocks"] == d["blocks"]
      and not any("kinds" in b for b in up["blocks"]))
v18 = {"schemaVersion": 18, "blocks": [blk(MINE, [M1, M2], "mine", True, kinds={POEM: False}), blk(M1, "x", kinds={POEM: True, OTHER: True}),
       blk(M2, "y", kinds={HOST: False}), blk(OTHER, [O1], "other", True), blk(O1, "z", kinds={POEM: True})]}
up = {b["id"]: b for b in M.upgrade(v18, now=None, new_id=None)["blocks"]}
same("v18 → v19: only a pericope has kinds: a yes inside carried up, the pericope's own answer winning, the rest gone",
     [up[i].get("kinds") for i in (MINE, M1, M2, OTHER, O1)], [{POEM: False, OTHER: True}, None, None, {POEM: True}, None])
schema = S.load_schema()
good = blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True, kinds={OTHER: False})
same("the schema takes a Kind, and kinds on a block", S.validate_instance(good, schema), [])
check("  and refuses a nameless kind, or an answer that isn't yes or no",
      S.validate_instance(blk(POEM, {"kind": " ", "blocks": []}), schema)
      and S.validate_instance(blk(M1, "x", kinds={POEM: "yes"}), schema))
check("  kinds is a header field the user writes (not readOnly)", "kinds" in S.editable_keys(schema))

# --- pure: answers, the merge point for a model's guesses, the header's text --------------------------------
same("parse_kinds: commas apart, 'not' before a no, a name once (the last word wins)",
     S.parse_kinds(" Poem,  not  letter , poem, ,to-do"), [("letter", False), ("poem", True), ("to-do", True)])
same("merge_kinds: guesses under your answers, which win", S.merge_kinds({POEM: False}, {POEM: True, OTHER: True}),
     {POEM: False, OTHER: True})
fresh()
b = B()
same("of_kind: the blocks you said are one", S.of_kind(b, POEM), [MINE])
same("  with a model's guesses merged under them (a later step's)", S.of_kind(b, POEM, {OTHER: {POEM: True}, MINE: {POEM: False}}),
     [MINE, OTHER])
same("kind_named: case and spacing aside", (S.kind_named(b, " POEM "), S.kind_named(b, "letter")), (POEM, None))
same("kind_of and display_title: its name", (S.kind_of(b[POEM]), S.display_title(b, POEM), S.kind_of(b[M1])), ("poem", "poem", None))

# --- the store: the header's kinds, made and undone ------------------------------------------------------------
fresh(kinds=False)
rec = S.set_kinds(MINE, "Poem, not letter")
b = B()
made = S.kind_ids(b)
same("set_kinds: each new name a new kind, an entry of its own, empty", sorted((S.kind_of(b[k]), b[k].get("entry"), S.children(b[k])) for k in made),
     [("Poem", True, []), ("letter", True, [])])
same("  the block's answers, yes and no", S.kinds_text(b, b[MINE]), "Poem, not letter")
check("  not an edit: the block's updated stays", b[MINE]["updated"] == T, b[MINE]["updated"])
rec2 = S.set_kinds(OTHER, "POEM")
same("  an existing name, any case: that kind, no new one", (len(S.kind_ids(B())), S.of_kind(B(), S.kind_named(B(), "poem"))), (2, [MINE, OTHER]))
redo = S.restore(rec2)
same("undo (restore its record): the answers as they were", S.kinds_of(B()[OTHER]), {})
S.restore(rec)
same("  and the kinds it made, gone: completely as before", (S.kinds_of(B()[MINE]), S.kind_ids(B())), ({}, []))
fresh()
try: S.set_kinds(POEM, "poem"); refused = False
except S.StoreError: refused = True
check("a kind can't be a kind of itself", refused)
S.set_kinds(MINE, "")
same("set_kinds '': its answers go, the kind stays", (S.kinds_of(B()[MINE]), S.kind_ids(B())), ({}, [POEM]))

# --- everything is a block: draft, words, backlinks, empty, delete ------------------------------------------------
fresh()
b = B()
same("the draft: a kind is drafted as its description's blocks", S.block_draft(b, POEM), f"{{{{block {PD}}}}}\na short piece in lines")
same("words: its description's (not its name)", b[POEM]["words"], 5)
S.commit(POEM, S.block_draft(b, POEM) + f"\n{{{{block}}}}\nwith a turn", [], final=True)
b = B()
same("  edited through the draft (as the editor saves): still a kind, a block added",
     (S.kind_of(b[POEM]), len(S.children(b[POEM])), S.own_text(b, POEM)), ("poem", 2, "a short piece in lines\nwith a turn"))
same("  and its words follow", b[POEM]["words"], 8)
same("kinds_text: the answers by name", S.kinds_text(B(), B()[MINE]), "poem")
found = S.backlinks(B(), POEM)
same("backlinks of a kind: the blocks of that kind", [(x["kind"], x["by"], x["home"]) for x in found], [("kind", MINE, MINE)])
same("  summed up", S.backlink_summary(found), "1 · 1 pericope with this tag")
S.set_kinds(OTHER, "not poem")
same("  a no isn't one", len(S.backlinks(B(), POEM)), 1)
check("an empty kind isn't 'empty': kept (it has its name)", not S.is_empty_untitled({POEM: blk(POEM, {"kind": "x", "blocks": []})}, POEM))
fresh()
S.set_kinds(MINE, "")
S.transact(S.editing(lambda data, blocks: blocks[POEM]["content"].update(blocks=[])))
S.cmd_migrate(None)
check("  migrate keeps an empty kind", POEM in B() and B()[POEM].get("entry"))
fresh()
S.delete_entry(POEM)
same("deleting a kind drops the answers about it", (POEM in B(), S.kinds_of(B()[MINE])), (False, {}))

# --- only a pericope has kinds; Turn into a quote leaves them where they were; a kind's own blocks too ---------------
fresh()
try: S.set_kinds(M1, "poem"); refused = False
except S.StoreError: refused = True
check("set_kinds on a block inside a pericope: refused (only a pericope has kinds)", refused)
try: S.set_kind(M1, POEM, True); refused = False
except S.StoreError: refused = True
check("  set_kind too", refused)
S.transact(S.editing(lambda data, blocks: blocks[M1].update(kinds={POEM: False})))
same("  a block moved inside one (as a paste might) loses its answers on the write", S.kinds_of(B()[M1]), {})
entry, _, rec = S.pop_out(M1)
b = B()
same("Turn into a quote inside a poem: the pericope still a poem, the new one not",
     (S.kinds_of(b[MINE]), S.kinds_of(b[entry]), S.quoted(b[M1])[0]), ({POEM: True}, {}, entry))
S.restore(rec)
entry, _, _ = S.pop_out(PD)
same("  a block of a kind's description: quoted there, the kind still a kind",
     (S.kind_of(B()[POEM]), S.quoted(B()[PD])[0]), ("poem", entry))
try: S.pop_out(POEM); refused = False
except S.StoreError: refused = True
check("  a kind itself can't be: it's a pericope of its own already", refused)

# --- two machines (the store a Loro document): answers merge kind by kind; a kind's description as a container -------
L2, K2 = "20261005T100000-e000", "20261005T100000-e001"
base = blk(M1, "same", kinds={POEM: True})
lap, other = copy.deepcopy(base), copy.deepcopy(base)
lap["kinds"] = {POEM: True, L2: True}
other["kinds"] = {K2: False}   # (the other machine took back "poem" and said "not K2")
same("merged: each side's answers kept, kind by kind", F.loro_merge(base, lap, other)["kinds"], {L2: True, K2: False})
kb = blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True)
kl = {**copy.deepcopy(kb), "content": {"kind": "poem", "blocks": [PD, L2]}, "updated": "2026-11-01T10:00:00-04:00"}
km = {**copy.deepcopy(kb), "content": {"kind": "poem", "blocks": [K2, PD]}, "updated": "2026-11-02T10:00:00-04:00"}
same("  a kind's description both sides added to: merged, still a kind", F.loro_merge(kb, kl, km)["content"],
     {"kind": "poem", "blocks": [K2, PD, L2]})

# --- search: a kind's name brings the kind first, then its blocks ------------------------------------------------
fresh()
S.set_kinds(OTHER, "poem")
lib = S.build_library(S.load_data())
refs = sorted((r for r, e in lib.items() if e["entry"]), reverse=True)
p = Search(lib, refs, inside=blocks_inside(lib, refs))
same("nothing typed: a kind's row, just its name (drawn blue)", [r[1] for r in p.rows() if r[0] == POEM], ["poem"])
p.query = "Poem"
same("its name typed (any case): the kind first, the blocks of that kind under it, oldest first",
     [(r[0], r[1]) for r in p.rows()[:3]], [(POEM, "poem"), (MINE, "  · mine"), (OTHER, "  · other")])
check("  each once", [r[0] for r in p.rows()].count(MINE) == 1, p.rows())
p.query = "poe"
check("  a part of it: an ordinary search (no blocks of that kind)", MINE not in [r[0] for r in p.rows()], p.rows())
link = Search(lib, refs)
link.query = "poem"
check("  Link to an entry (not a search over blocks): no kind-first rows", [r[0] for r in link.rows()] == [POEM], link.rows())

# --- renaming a kind: its title field is its name --------------------------------------------------------------
fresh()
S.set_kinds(HOST, "letter")
rec = S.rename_kind(POEM, "  Free   verse ")
same("rename_kind: the name, its spacing tidied", S.kind_of(B()[POEM]), "Free verse")
check("  everything reads it: the title, the answers' text, a search", S.display_title(B(), POEM) == "Free verse"
      and S.kinds_text(B(), B()[MINE]) == "Free verse" and S.kind_named(B(), "free verse") == POEM)
S.restore(rec)
same("  undone (restore): its old name", S.kind_of(B()[POEM]), "poem")
for name, why in (("  ", "a tag needs a name"), ("LETTER", "there's a tag called letter already")):
    try: S.rename_kind(POEM, name); got = None
    except S.StoreError as e: got = str(e)
    same(f"  refused: {name!r}", got, why)
S.rename_kind(POEM, "Poem")
same("  its own name in another case: fine", S.kind_of(B()[POEM]), "Poem")
# --- every pericope's header says its type -----------------------------------------------------------------
same("block_type over the content cases", [S.block_type(blk(M1, c)) for c in
     ("text", [], {"image": "a.png"}, {"quote": M1}, {"kind": "poem", "blocks": []})], ["text", "block", "image", "quote", "kind"])
same("type_label: a kind's says which", [S.type_label(blk(M1, c)) for c in ({"kind": "poem", "blocks": []}, [PD])], ["tag: poem", "block"])
b = B()
same("  a pericope's, given the blocks: its one block's type, else 'pericope'",
     [S.type_label(b[MINE], b), S.type_label(b[OTHER], b), S.type_label({**b[OTHER], "content": []}, b), S.type_label(b[M1], b)],
     ["pericope", "text", "pericope", "text"])
# --- a model's guesses: applied from 0.9, maybes to review from 0.5 (only pericopes) ------------------------------
THIRD, T1, LET = "20261005T100000-c000", "20261005T100000-c001", "20261005T100000-e000"
def g(p, kind_at=T, block_at=T): return [p, kind_at, block_at]
F.store(blk(MINE, [M1, M2], "mine", True), blk(M1, "roses are red"), blk(M2, "buy milk"), blk(OTHER, [O1], "other", True),
        blk(O1, "an old pond"), blk(THIRD, [T1], "third", True), blk(T1, "a third thing"),
        blk(POEM, {"kind": "poem", "blocks": [PD]}, entry=True), blk(PD, "a short piece in lines"),
        blk(LET, {"kind": "letter", "blocks": []}, entry=True))
b = B()
data = {"guesses": {POEM: {M1: g(0.99), M2: g(0.95), O1: g(0.7), MINE: g(0.95), OTHER: g(0.6), PD: g(0.8, block_at="2026-10-02T10:00:00-04:00"),
                           LET: g(0.97), POEM: g(0.99)}, LET: {MINE: g(0.99)}}}
same("maybes: pericopes, unanswered, current, 0.5 ≤ p < 0.9, likeliest first", S.maybes(data, b, POEM), [(OTHER, 0.6)])
same("  thresholds", (S.MAYBE_AT, S.GUESS_AT), (0.5, 0.9))
same("  under 0.5: not a maybe", S.maybes({"guesses": {POEM: {MINE: g(0.49)}}}, b, POEM), [])
same("  ties: the oldest first", S.maybes({"guesses": {POEM: {OTHER: g(0.8), MINE: g(0.8)}}}, b, POEM), [(MINE, 0.8), (OTHER, 0.8)])
same("  another kind's: its own (0.99: applied, not a maybe)", S.maybes(data, b, LET), [])
same("  nothing malformed counts", [S.maybes(x, b, POEM) for x in (None, {}, {"guesses": {POEM: []}})], [[]] * 3)
same("is_applied: any guess from 0.9, a pericope's too, whichever model",
     [S.is_applied(b, M2, POEM, set()), S.is_applied(b, MINE, POEM, set()), S.is_applied(b, MINE, POEM, {POEM})], [True, True, True])
learned = {"guesses": {POEM: {MINE: g(0.95), OTHER: g(0.7)}}, "sources": {POEM: {"source": "learned"}, LET: {"source": "qwen"}}}
same("learned: the kinds whose source is learned", S.learned(learned), {POEM})
same("  anything malformed: none", [S.learned(x) for x in (None, {}, {"sources": []}, {"sources": {POEM: "learned"}})], [set()] * 4)
same("  a learned kind's maybes: only under 0.9", S.maybes(learned, b, POEM), [(OTHER, 0.7)])
lib = S.build_library(S.load_data())
refs = sorted(r for r, e in lib.items() if e["entry"])
rec = S.set_kind(OTHER, POEM, False)[1]
same("set_kind: one answer (a review's no)", S.kinds_of(B()[OTHER]), {POEM: False})
S.restore(rec)
same("  undone", S.kinds_of(B()[OTHER]), {})
check("  not an edit: updated stays", B()[OTHER]["updated"] == T)

# --- kinds a model proposes ---------------------------------------------------------------------------------------
P = [f"2026100{n}T100000-f000" for n in range(1, 8)]
C = [f"2026100{n}T100000-f001" for n in range(1, 8)]
blocks = [x for n in range(7) for x in (blk(P[n], [C[n]], f"day {n + 1}", True), blk(C[n], f"today I wrote thing {n + 1}"))]
blocks[0]["kinds"] = {POEM: True}
F.store(*blocks, blk(POEM, {"kind": "poem", "blocks": []}, entry=True))
JOURNAL = {"id": "j1", "name": "journal entry", "description": "Written day by day, as it comes.", "members": P[:6], "typical": P[1:4]}
b = B()
cover = S.kind_cover(b, {})
same("kind_cover: a yes said", cover, {P[0]})
gl = {"guesses": {POEM: {P[1]: [0.95, b[POEM]["updated"], b[P[1]]["updated"]]}}, "sources": {POEM: {"source": "learned"}}}
same("  and a guess applied", S.kind_cover(b, gl), {P[0], P[1]})
got = S.open_proposals({"proposals": [JOURNAL]}, b, {}, cover)
same("open_proposals: its members now only the uncovered pericopes", [x["members"] for x in got], [P[1:6]])
same("  the rest as given", (got[0]["name"], got[0]["description"], got[0]["typical"]), ("journal entry", JOURNAL["description"], P[1:4]))
same("  fewer than 5 uncovered: not offered", S.open_proposals({"proposals": [JOURNAL]}, b, {}, S.kind_cover(b, gl)), [])
same("  a block that isn't a pericope (or is gone) doesn't count",
     S.open_proposals({"proposals": [{**JOURNAL, "members": P[1:5] + [C[5], "20261010T100000-0000"]}]}, b, {}, cover), [])
same("  a kind of that name now (case aside): not offered", S.open_proposals({"proposals": [{**JOURNAL, "name": "Poem"}]}, b, {}, cover), [])
same("  dismissed by name", S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "Journal Entry", "members": []}]}, cover), [])
same("  dismissed: half its members or more in common, under another name",
     S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "diary", "members": P[:4]}]}, cover), [])
same("  a dismissal sharing fewer: still offered",
     len(S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "diary", "members": P[:2]}]}, cover)), 1)
same("  anything malformed counts for nothing", [S.open_proposals(x, b, {}, cover) for x in (None, {}, {"proposals": {}},
     {"proposals": [{"name": "x"}]}, {"proposals": [{"name": "  ", "members": P}]})], [[]] * 5)
kid = S.kind_from_proposal(got[0])
same("kind_from_proposal: a kind, a pericope, named as proposed", (S.kind_of(B()[kid]), B()[kid].get("entry")), ("journal entry", True))
same("  its description: the sentence, then live quotes of the typical members", [B()[i]["content"] for i in B()[kid]["content"]["blocks"]],
     [JOURNAL["description"]] + [{"quote": i} for i in P[1:4]])
check("  a second time: refused, the name's taken", "already" in (F.refused(S.kind_from_proposal, got[0]) or ""))
S.dismiss_proposal(got[0])
d = S.load_dismissed()["dismissed"]
same("dismiss_proposal: kept beside the store, by name and members", (d[0]["name"], d[0]["members"], bool(d[0]["at"])), ("journal entry", P[1:6], True))
check("the store validates throughout", not S.invalid(S.load_data(), S.load_schema()), S.invalid(S.load_data(), S.load_schema()))
F.report()

