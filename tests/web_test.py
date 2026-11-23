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
same("home: every pericope, a line each, in the recommendation's order", (code, home["count"], sorted(r["key"] for r in home["rows"])), (200, 3, [A, B, C]))
# visits from the page's attention (POST /api/visit): kept by the core, written when they end or on leaving
same("attention on a pericope and a block in it", [call("POST", "/api/visit", {"pericope": A})[0],
     call("POST", "/api/visit", {"block": A1, "flags": "cw", "ago": 3})[0]], [200, 200])
b = S.index(S.load_data())
check("  not written yet (a visit under way)", not b[A1].get("visits"), b[A1].get("visits"))
call("POST", "/api/visit", {"flush": True})
b = S.index(S.load_data())
check("  left: written, the block's flags as said, carried up to its pericope", "cw" in "".join(f for _, f in S.visits(b[A1]))
      and "o" in "".join(f for _, f in S.visits(b[A])) and "c" in "".join(f for _, f in S.visits(b[A])), (b[A1].get("visits"), b[A].get("visits")))
same("  not an edit: nothing else about them changed", S.content_hash(b, A) == S.content_hash(S.index(S.load_data()), A), True)
code, ex = call("GET", f"/api/exits/{B}")
same("exits from beta: alpha, which quotes it", (code, [r["key"] for r in ex["rows"]][:1]), (200, [A]))
code, ex = call("GET", f"/api/exits/{A}")
check("  from alpha: not beta, already on its page", code == 200 and B not in [r["key"] for r in ex["rows"]], ex)
same("  not a pericope: 404", call("GET", "/api/exits/20991001T100000-0000")[0], 404)
code, p = call("GET", f"/api/pericope/{A}")
same("a pericope: its blocks as a tree", [(n["t"], n.get("id")) for n in p["children"]], [("text", A1), ("quote", QA), ("text", A2)])
same("  a block of text, its lines", p["children"][0]["text"], "first line\nsecond line")
q = p["children"][1]
same("  a quote: its target, where it lives, what it shows", (q["target"], q["home"], q["body"]), (B, B, [{"t": "text", "text": "beta's words"}]))
same("  the header", (p["shown"], p["type"], p["backlinks"], p["kinds"]), ("alpha", "pericope", "", ""))
same("  every field, empty or not: last visited, created", ("visited" in p, "created" in p), (True, True))
code, pb = call("GET", f"/api/pericope/{B}")
same("  backlinks, when something points at it", pb["backlinks"], "1 · 1 quote")
code, pc = call("GET", f"/api/pericope/{C}")
same("  a container, its blocks inside", pc["children"], [{"t": "container", "id": C1,
                                                         "children": [{"t": "text", "id": C2, "text": "nested", "links": [], "para": None}]}])

# the kinds view (2026-11-22): + new kind, a kind's members (your answers, newest first), on its page too
code, nk = call("POST", "/api/act", {"do": "newkind", "name": "  song "})
same("+ new kind: made, its name tidied", (code, S.kind_of(S.index(S.load_data())[nk["kind"]])), (200, "song"))
same("  the same name again (case aside): that one, none made", call("POST", "/api/act", {"do": "newkind", "name": "Song"})[1]["kind"], nk["kind"])
same("  no name: refused", call("POST", "/api/act", {"do": "newkind", "name": " "})[0] >= 400, True)
call("POST", "/api/act", {"do": "kind", "block": A, "kind": nk["kind"], "answer": True})
call("POST", "/api/act", {"do": "kind", "block": C, "kind": nk["kind"], "answer": True})
code, said = call("POST", "/api/act", {"do": "kind", "block": C2, "kind": nk["kind"], "answer": True})
same("  a block inside a pericope: refused (only a pericope has kinds)", (code >= 400, "pericope" in said.get("error", "")), (True, True))
call("POST", "/api/act", {"do": "kind", "block": B, "kind": nk["kind"], "answer": False})
code, kv = call("GET", "/api/kinds?members=1")
song = next(k for k in kv["kinds"] if k["id"] == nk["kind"])
same("  its members: yes answers only, newest first, each opening as itself",
     [(m["key"], m["open"], m["dim"]) for m in song["members"]], [(C, C, False), (A, A, False)])
same("  the pericopes of no kind: none of a yes, not a kind, newest first", [m["key"] for m in kv["unkinded"]],
     sorted((i for i, b in S.index(S.load_data()).items() if b.get("entry") and i not in (A, C) and S.kind_of(b) is None), reverse=True))
same("  without members=1: just names", "members" in call("GET", "/api/kinds")[1]["kinds"][0], False)
same("  on the kind's own page too", [m["key"] for m in call("GET", f"/api/pericope/{nk['kind']}")[1]["members"]], [C, A])
same("  not a kind: none", call("GET", f"/api/pericope/{A}")[1]["members"], None)
up = {i: b.get("updated") for i, b in S.index(S.load_data()).items()}
S.GUESSES_PATH.write_text(json.dumps({"model": "t", "guesses": {nk["kind"]: {B: [0.95, up[nk["kind"]], up[B]], C: [0.6, up[nk["kind"]], up[C]]}}}))
call("POST", "/api/act", {"do": "kind", "block": B, "kind": nk["kind"], "answer": None})
call("POST", "/api/act", {"do": "kind", "block": C, "kind": nk["kind"], "answer": None})
up = {i: b.get("updated") for i, b in S.index(S.load_data()).items()}
S.GUESSES_PATH.write_text(json.dumps({"model": "t", "guesses": {nk["kind"]: {B: [0.95, up[nk["kind"]], up[B]], C: [0.6, up[nk["kind"]], up[C]]}}}))
song = next(k for k in call("GET", "/api/kinds?members=1")[1]["kinds"] if k["id"] == nk["kind"])
same("  then the model's: sure (dim, its p), then maybes", [(m["key"], m["dim"], m.get("p"), m.get("maybe", False)) for m in song["members"]],
     [(A, False, None, False), (B, True, 0.95, False), (C, True, 0.6, True)])
S.GUESSES_PATH.unlink()
for blk_ in (A, C, B):
    call("POST", "/api/act", {"do": "kind", "block": blk_, "kind": nk["kind"], "answer": None})

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
check("  in home's list", any(r["key"] == pic for r in home["rows"]), home["rows"])
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
same("home's list: every pericope, not just the first few", len(W.home_json(S.build_library(many))), 20)
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

# only this machine's page may use it (the audit of 2026-11-19): Host, Origin, and JSON for what changes something
PORT = httpd.server_address[1]
def raw(method, path, body=b"", headers={}):
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in {"Host": f"127.0.0.1:{PORT}", **headers}.items():
        if v is not None:
            c.putheader(k, v)
    c.putheader("Content-Length", str(len(body)))
    c.endheaders(body)
    r = c.getresponse()
    out = r.status, r.read()
    c.close()
    return out
entries = lambda: sum(1 for b in S.load_data()["blocks"] if b.get("entry"))
n = entries()
make = json.dumps({"title": "from elsewhere"}).encode()
same("a POST from another site's page (a foreign Origin): refused, nothing made",
     (raw("POST", "/api/pericope", make, {"Content-Type": "application/json", "Origin": "https://evil.example"})[0], entries()), (403, n))
same("  a plain-text POST (no preflight needed): refused, nothing made",
     (raw("POST", "/api/pericope", make, {"Content-Type": "text/plain;charset=UTF-8"})[0], entries()), (403, n))
same("  a form's POST: refused", raw("POST", "/api/act", b"do=delete", {"Content-Type": "application/x-www-form-urlencoded"})[0], 403)
same("  no Content-Type: refused", raw("PUT", "/api/keys", b'{"keys": {}}', {"Content-Type": None})[0], 403)
same("  a wrong Host (a rebound DNS name): refused, even to read", raw("GET", "/api/home", headers={"Host": f"evil.example:{PORT}"})[0], 403)
same("  the right host on another port: refused", raw("GET", "/api/home", headers={"Host": f"127.0.0.1:{PORT + 1}"})[0], 403)
same("  no Host at all: refused", raw("GET", "/api/home", headers={"Host": None})[0], 403)
same("  Origin null (a sandboxed frame, a file): refused", raw("GET", "/api/home", headers={"Origin": "null"})[0], 403)
same("  the page's own: 127.0.0.1 or localhost, with or without an Origin", [
    raw("GET", "/api/home")[0], raw("GET", "/api/home", headers={"Host": f"localhost:{PORT}", "Origin": f"http://localhost:{PORT}"})[0],
    raw("GET", "/api/home", headers={"Origin": f"http://127.0.0.1:{PORT}"})[0], raw("GET", "/")[0],
    raw("POST", "/api/pericope", make, {"Content-Type": "application/json; charset=utf-8", "Origin": f"http://127.0.0.1:{PORT}"})[0]],
    [200, 200, 200, 200, 200])
same("  a dropped picture's bytes (image/*) still taken, at /api/picture only",
     (raw("POST", "/api/picture", png(), {"Content-Type": "image/png", "X-Name": "dot.png"})[0],
      raw("POST", "/api/pericope", png(), {"Content-Type": "image/png"})[0]), (200, 403))
same("  refusal is pure: the reasons", [W.refusal("GET", "/", "127.0.0.1:1", None, None, 1), W.refusal("GET", "/", "x:1", None, None, 1),
     W.refusal("GET", "/", "localhost:1", "http://x", None, 1), W.refusal("POST", "/api/act", "localhost:1", None, "text/plain", 1)],
     [None, "not this machine's page (Host)", "not this machine's page (Origin)", "expected Content-Type: application/json"])
httpd.shutdown()

F.report("WEB")
