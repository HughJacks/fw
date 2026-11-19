# the web editor's core (fw_web.py, 2026-11-17): the page sees the store only as JSON, and saves drafts in
# fw's draft format through the same commit the terminal uses. On a throwaway store, the server in a thread.
import json, os, sys, urllib.request, urllib.error
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("t/web.json", clean=True)
sys.path.insert(0, F.DEV)
import fw_web as W

A, A1, A2, QA, B, B1, C, C1, C2 = ("20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002",
                                   "20261001T100000-a003", "20261002T100000-b000", "20261002T100000-b001",
                                   "20261003T100000-c000", "20261003T100000-c001", "20261003T100000-c002")
F.write_store([blk(A, [A1, QA, A2], "alpha"), blk(A1, "first line\nsecond line"), blk(QA, {"quote": B}), blk(A2, "after"),
               blk(B, [B1], "beta"), blk(B1, "beta's words"),
               blk(C, [C1], "gamma"), blk(C1, [C2]), blk(C2, "nested")], [A, B, C], version=9)
S.cmd_migrate(None)
httpd = W.serve(0)
URL = f"http://127.0.0.1:{httpd.server_address[1]}"
def call(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

code, home = call("GET", "/api/home")
same("home: every pericope, in the garden's order", (code, home["count"], sorted(r["key"] for r in home["rows"])), (200, 3, [A, B, C]))
code, p = call("GET", f"/api/pericope/{A}")
same("a pericope: its blocks as a tree", [(n["t"], n.get("id")) for n in p["children"]], [("text", A1), ("quote", QA), ("text", A2)])
same("  a block of text, its lines", p["children"][0]["text"], "first line\nsecond line")
q = p["children"][1]
same("  a quote: its target, where it lives, what it shows", (q["target"], q["home"], q["body"]), (B, B, [{"t": "text", "text": "beta's words"}]))
same("  the header", (p["shown"], p["type"], p["backlinks"], p["kinds"]), ("alpha", "block", "", ""))
code, pb = call("GET", f"/api/pericope/{B}")
same("  backlinks, when something points at it", pb["backlinks"], "1 · 1 quote")
code, pc = call("GET", f"/api/pericope/{C}")
same("  a container, its blocks inside", pc["children"], [{"t": "container", "id": C1, "para": None,
                                                         "children": [{"t": "text", "id": C2, "text": "nested", "links": [], "para": None}]}])

# saving: a draft, as the page writes it (web/src/draft.js)
NEW = "20261117T090000-0001"
draft = f"{{{{block {A1}}}}}\nfirst line, changed\n{{{{quote {B} {QA}}}}}\n{{{{block {NEW}}}}}\na new block\n{{{{block {A2}}}}}\nafter"
code, r = call("PUT", f"/api/pericope/{A}", {"draft": draft, "base": p["base"]})
b = S.index(S.load_data())
same("a save: the draft into the store, by the terminal's commit", (code, S.children(b[A]), b[A1]["content"], b[NEW]["content"]),
     (200, [A1, QA, NEW, A2], "first line, changed", "a new block"))
code, r2 = call("PUT", f"/api/pericope/{A}", {"draft": draft, "base": p["base"]})
same("  a save over a change made elsewhere is refused", (code, "another session" in r2.get("error", "")), (409, True))
code, _ = call("PUT", f"/api/pericope/{A}", {"draft": draft, "base": r["base"], "title": "Alpha, renamed"})
same("  the title, from the header", S.index(S.load_data())[A]["title"], "Alpha, renamed")
code, _ = call("PUT", f"/api/pericope/{A}", {"draft": None, "base": r["base"], "title": "Alpha, the title alone"})
same("  the title alone (no draft: the text unchanged): saved too", S.index(S.load_data())[A]["title"], "Alpha, the title alone")

code, made = call("POST", "/api/pericope", {"title": None})
check("a new pericope", code == 200 and made["id"] in S.index(S.load_data()), made)
code, r = call("PUT", f"/api/pericope/{made['id']}", {"draft": "", "base": None, "final": True})
check("  left empty and untitled: discarded, as the terminal does", code == 200 and r["gone"], r)
# home's waiting pericope (2026-11-19): made on its first key, then saved into at once with the base it came with
code, made = call("POST", "/api/pericope", {"title": None})
same("  made: its base comes with its id", (code, made["base"]), (200, call("GET", f"/api/pericope/{made['id']}")[1]["base"]))
NEWB = "20261119T090000-0001"
code, r = call("PUT", f"/api/pericope/{made['id']}", {"draft": f"{{{{block {NEWB}}}}}\nfirst words", "base": made["base"]})
same("  a save on that base: taken", (code, S.index(S.load_data())[NEWB]["content"]), (200, "first words"))

code, s = call("GET", "/api/search?q=nested")
same("the search: the terminal's rows (blocks under where they live: the container, titled by its text, and its block)",
     [(x["key"], x["label"].strip(), x["open"]) for x in s["rows"]][1:], [(C, "gamma", C), (C1, "· nested", C), (C2, "· nested", C)])
# the / menu's: a new quote's drawing, a block popped out, a quote masked to a block, a picture
code, q = call("GET", f"/api/quote?target={B}")
same("a new quote: what it shows, what it holds (written through)", (code, q["target"], q["tree"][0]["text"]), (200, B, "beta's words"))
code, made = call("POST", "/api/popout", {"block": C2})
b = S.index(S.load_data())
check("pop out: the block a pericope of its own, quoted where it was", code == 200 and b[made["id"]].get("entry")
      and S.quoted(b[S.children(b[C1])[0]]) == (made["id"], None), (code, made))
code, m = call("POST", "/api/maskto", {"quote": QA, "block": B1})
same("mask to: the quote shows just that block (all beta holds: so no mask is kept)", (code, m.get("masked"), [x.get("text") for x in m.get("body", [])]),
     (200, False, ["beta's words"]))
import struct, zlib
def png():
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x80\x80" * 2)) + chunk(b"IEND", b""))
req = urllib.request.Request(URL + "/api/picture", method="POST", data=png(), headers={"Content-Type": "image/png", "X-Name": "dot.png"})
with urllib.request.urlopen(req) as r:
    pic = json.loads(r.read())["id"]
b = S.index(S.load_data())
check("a picture's bytes (dropped): a picture pericope", b[pic].get("entry") and S.image_of(b[pic]), b.get(pic))
code, home = call("GET", "/api/home")
check("  not in the garden (searching finds it)", all(r["key"] != pic for r in home["rows"]), home["rows"])
same("  its preview: it", W.preview(b, pic), [{"t": "image", "file": S.image_of(b[pic])}])
# a new quote: never refused (the user, 2026-11-19: the data model allows any quote; the drawing decides what shows)
code, r = call("GET", f"/api/quote?target={B}&into={A}&depth=0")
same("a quote of another pericope, here: made", code, 200)
# (a cycle is made, the user, 2026-11-19: drawn as far as the cycle, then a ↻ stand-in, as a ⋯ past the depth)
notes = lambda body: [x.get("text", "") for x in body if x.get("t") == "note"] + [n for x in body if x.get("t") == "quote" for n in notes(x.get("body", []))]
code, r = call("GET", f"/api/quote?target={A}&into={A}&depth=0")
check("  of this pericope, in it: made, a ↻ where it would show itself", code == 200 and any(n.startswith("↻") for n in notes(r["body"])), (code, r))
code, r = call("GET", f"/api/quote?target={A}&into={B}&depth=0")
check("  of a pericope quoting this one (A quotes B), into B: made, B a ↻ inside it", code == 200 and any(n.startswith("↻") for n in notes(r["body"])), (code, r))
code, r = call("GET", f"/api/quote?target={B}&into={A}&depth={W.MAX_DEPTH}")
check("  already as deep as quotes are shown: made, a ⋯ in its place", code == 200 and any(n.startswith("⋯") for n in notes(r["body"])), (code, r))
code, found = call("GET", "/api/search?q=picture")
check("  searching finds it", any(r.get("key") == pic or r.get("open") == pic for r in found["rows"]), found["rows"])
many = {"blocks": [{"id": f"20261001T1000{n:02d}-0000", "entry": True, "content": f"pericope {n}", "created": "2026-10-01T10:00:00-04:00"}
                   for n in range(20)]}
same("the garden: its first 12 only", len(W.home_json(S.build_library(many))), W.GARDEN)
P, P1, PQ, P2 = "20261117T100000-e000", "20261117T100000-e001", "20261117T100000-e002", "20261117T100000-e003"
pblocks = {**b, P: {"id": P, "content": [P1, PQ, P2]}, P1: {"id": P1, "content": "before  the\npicture"},
           PQ: {"id": PQ, "content": {"quote": pic}}, P2: {"id": P2, "content": "after it"}}
same("  a card's preview: its text and pictures in order, a quoted picture where it's quoted",
     W.preview(pblocks, P), [{"t": "text", "text": "before the picture"}, {"t": "image", "file": S.image_of(b[pic])}, {"t": "text", "text": "after it"}])
code, bad = call("POST", "/api/picture", {"url": "not a link"})
same("  a link that isn't one: refused, saying why", (code, "web address" in bad.get("error", "")), (409, True))

# the Ctrl+/ menu's actions, each a store function, each with its undo record
code, r = call("POST", "/api/act", {"do": "lock", "quote": QA, "on": True})
check("act lock: the quote locked", code == 200 and S.quote_lock(S.index(S.load_data())[QA]), r)
code, back = call("POST", "/api/restore", {"record": r["record"]})
check("  restore: taken back (and its inverse comes back)", code == 200 and not S.quote_lock(S.index(S.load_data())[QA]) and back["record"], back)
code, r = call("POST", "/api/act", {"do": "show", "quote": QA, "show": ["title"]})
same("act show: its top line", S.quote_show(S.index(S.load_data())[QA]), ["title"])
code, r = call("POST", "/api/act", {"do": "detach", "quote": QA})
check("act detach: a plain copy, no longer live", code == 200 and isinstance(S.index(S.load_data())[QA]["content"], str), S.index(S.load_data())[QA])
code, r = call("POST", "/api/act", {"do": "nothing"})
same("  an action that isn't one", code, 404)

code, st = call("GET", "/api/stamp")
check("the stamp: the store's", code == 200 and st["stamp"] == S.DATA_PATH.stat().st_mtime_ns)
code, page = 0, ""
with urllib.request.urlopen(URL + "/") as r:
    code, page = r.status, r.read().decode()
check("the page itself", code == 200 and "/dist/app.js" in page)
code, bad = call("GET", "/images/../freewrites.json")
same("  pictures only from the images folder", code, 404)
httpd.shutdown()

F.report("WEB")
