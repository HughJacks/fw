# kinds a model proposes (a model outside fw names each pericope's form; a form shared by enough pericopes no kind
# covers is proposed, in kind-proposals.json, written beside the store by a model outside fw). Home (the garden) offers one,
# a dim card after "+ new pericope": Enter makes it a kind (its description the drafted sentence and live quotes of typical members)
# and goes straight into reviewing its members; ^D dismisses it (asks y), kept in kind-dismissed.json beside the store.
# Pure: fw_block.open_proposals (what's still worth offering), kind_cover (what a kind covers already).
import json, os, sys
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, LEFT, ENTER, ESC, QUIT as Q
F.pyte.graphics.TEXT[2] = "+blink"   # (pyte has no dim: SGR 2 reads as blink here)
S = F.use_store("t/proposals.json", clean=True)

T = "2026-10-01T10:00:00-04:00"
P = [f"2026100{n}T100000-a000" for n in range(1, 8)]          # seven pericopes
C = [f"2026100{n}T100000-a001" for n in range(1, 8)]          # a text block in each
POEM = "20261009T100000-d000"
ENV = {"PATH": os.path.abspath("fakebin") + ":" + os.environ["PATH"], "CLIP": os.path.abspath("t/mac.txt")}
HERE = os.path.dirname(os.environ["FW_DATA"])
PROPOSALS, DISMISSED, GUESSES = (os.path.join(HERE, f) for f in ("kind-proposals.json", "kind-dismissed.json", "kind-guesses.json"))

def blk(i, content, title=None, entry=False, **more):
    return {"id": i, "title": title, **({"entry": True} if entry else {}), "content": content, "words": 0,
            "created": T, "updated": T, **more}
def fresh():
    blocks = [b for n in range(7) for b in (blk(P[n], [C[n]], f"day {n + 1}", True), blk(C[n], f"today I wrote thing {n + 1}"))]
    blocks += [blk(POEM, {"kind": "poem", "blocks": []}, entry=True)]
    blocks[0]["kinds"] = {POEM: True}                                       # P[0]: a poem already
    json.dump({"schemaVersion": 17, "blocks": blocks}, open(os.environ["FW_DATA"], "w"))
    S.cmd_migrate(None)
    for f in (PROPOSALS, DISMISSED, GUESSES, "t/mac.txt", S.CLIP_PATH):
        if os.path.exists(f): os.remove(f)
def B(): return S.index(S.load_data())
def propose(*ps):
    json.dump({"model": "m", "proposals": list(ps)}, open(PROPOSALS, "w"))
JOURNAL = {"id": "j1", "name": "journal entry", "description": "Written day by day, as it comes.",
           "members": P[:6], "typical": P[1:4]}
def bar(t): return t.row(t.scr.lines - 1)
def row_of(t, text): return next((y for y in range(t.scr.lines) if text in t.row(y)), None)

# --- pure: what's still worth offering -------------------------------------------------------------------------------
fresh()
b = B()
cover = S.kind_cover(b, {})
same("kind_cover: a yes said", cover, {P[0]})
g = {"guesses": {POEM: {P[1]: [0.95, B()[POEM]["updated"], B()[P[1]]["updated"]]}}, "sources": {POEM: {"source": "learned"}}}
same("  and a guess applied (a learned kind's, ≥ 0.9)", S.kind_cover(b, g), {P[0], P[1]})
got = S.open_proposals({"proposals": [JOURNAL]}, b, {}, cover)
same("open: its members now only the uncovered pericopes", [p["members"] for p in got], [P[1:6]])
same("  the rest as given", (got[0]["name"], got[0]["description"], got[0]["typical"]), ("journal entry", JOURNAL["description"], P[1:4]))
same("  fewer than 5 uncovered: not offered", S.open_proposals({"proposals": [JOURNAL]}, b, {}, S.kind_cover(b, g)), [])
same("  a block that isn't a pericope (or is gone) doesn't count",
     S.open_proposals({"proposals": [{**JOURNAL, "members": P[1:5] + [C[5], "20261010T100000-gone"]}]}, b, {}, cover), [])
same("  a kind of that name now (case aside): not offered", S.open_proposals({"proposals": [{**JOURNAL, "name": "Poem"}]}, b, {}, cover), [])
same("  dismissed by name", S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "Journal Entry", "members": []}]}, cover), [])
same("  dismissed: half its members or more in common, under another name",
     S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "diary", "members": P[:4]}]}, cover), [])
same("  a dismissal sharing fewer: still offered",
     len(S.open_proposals({"proposals": [JOURNAL]}, b, {"dismissed": [{"name": "diary", "members": P[:2]}]}, cover)), 1)
same("  anything malformed counts for nothing",
     [S.open_proposals(x, b, {}, cover) for x in (None, {}, {"proposals": {}}, {"proposals": [{"name": "x"}]},
                                                 {"proposals": [{"name": "  ", "members": P}]})], [[]] * 5)

# --- the store: a kind made from one; a dismissal kept ----------------------------------------------------------------
kid = S.kind_from_proposal(got[0])
k = B()[kid]
same("kind_from_proposal: a kind, a pericope, named as proposed", (S.kind_of(k), k.get("entry")), ("journal entry", True))
parts = [B()[i]["content"] for i in k["content"]["blocks"]]
same("  its description: the sentence, then live quotes of the typical members", parts,
     [JOURNAL["description"]] + [{"quote": i} for i in P[1:4]])
try:
    S.kind_from_proposal(got[0]); check("  a second time: refused", False)
except S.StoreError as e:
    check("  a second time: refused, the name's taken", "already" in str(e), str(e))
check("the store validates", not S.invalid(S.load_data(), S.load_schema()), S.invalid(S.load_data(), S.load_schema()))
S.dismiss_proposal(got[0])
d = S.load_dismissed()["dismissed"]
same("dismiss_proposal: kept beside the store, by name and members", (d[0]["name"], d[0]["members"], bool(d[0]["at"])),
     ("journal entry", P[1:6], True))

# --- home: the row; Enter makes the kind and reviews its members -------------------------------------------------------
fresh()
propose(JOURNAL)
t = F.fw("open", rows=24, cols=80, env=ENV)
y = row_of(t, "a kind: journal entry")
x = t.row(y).index("a kind: journal entry") if y is not None else 0
check("the garden offers it, a dim card after + new pericope", y is not None and "new pericope" in t.row(y)
      and t.row(y).index("new pericope") < x and t.cell(y, x).blink and " proposed " in t.row(y - 1), t.text())
check("  saying how many, and what Enter and ^D do", "5 pericopes alike" in t.text() and "make it a kind" in t.text()
      and "^D dismiss it" in t.text(), t.text())
check("  a pericope still selected first, not it", not t.cell(y, x).reverse, t.text())
t.key(LEFT)
check("  ← onto it: selected", t.cell(y, x).reverse, t.text())
t.key(ENTER)
kid = S.kind_named(B(), "journal entry")
check("Enter: the kind is made", kid is not None and B()[kid].get("entry"), [S.kind_of(x) for x in B().values()])
check("  straight into its members, one at a time, no %", "journal entry? · 1 of 5" in bar(t) and "thing 2" in t.text(), bar(t))
check("  the kind waits on the trail", "journal entry ›" in bar(t), bar(t))
t.key(ENTER); t.settle()
same("  Enter: it is one", S.kinds_of(B()[P[1]]), {kid: True})
t.key(F.BS); t.settle()
same("  Backspace: it isn't", S.kinds_of(B()[P[2]]), {kid: False})
t.key(Q); t.settle()
check("^Q: back on the new kind, the bar says how it went", "reviewed: 1 yes, 1 no · 3 left" in bar(t) and "kind: journal entry" in t.text(), bar(t))
t.key(Q, ESC); t.done()
t = F.fw("open", rows=24, cols=80, env=ENV)
check("home again: not offered (a kind has that name now)", "a kind:" not in t.text(), t.text())
t.key(ESC); t.done()

# --- home: ^D dismisses it, once asked ---------------------------------------------------------------------------------
fresh()
propose(JOURNAL)
t = F.fw("open", rows=24, cols=80, env=ENV)
t.key(LEFT, "\x04")
check("^D on it asks first", "dismiss the kind 'journal entry'?" in bar(t), bar(t))
t.key("n")
check("  any other key keeps it", "kept" in bar(t) and "a kind: journal entry" in t.text() and not os.path.exists(DISMISSED), t.text())
t.key("\x04", "y")   # (after "kept", still on it: home as it was left)
check("  y dismisses it: gone from home", "dismissed the kind 'journal entry'" in bar(t) and "a kind:" not in t.text(), t.text())
same("  kept in kind-dismissed.json", [d["name"] for d in json.load(open(DISMISSED))["dismissed"]], ["journal entry"])
check("  no kind made", S.kind_named(B(), "journal entry") is None)
t.key(ESC); t.done()
t = F.fw("open", rows=24, cols=80, env=ENV)
check("  not offered again", "a kind:" not in t.text(), t.text())
t.key(ESC); t.done()

F.report("PROPOSALS")
