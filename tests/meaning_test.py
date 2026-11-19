# search by meaning (2026-11-17): a search service answers which blocks are near what's typed, asked after
# a pause, in the background (fw_meaning); home and Quote a block mix the answer into the list by rank (fw_picker.fuse);
# no service, the title search as ever. A fake one here: a little HTTP server with fixed answers.
import http.server, json, os, sys, threading, urllib.parse
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, ESC, ENTER, QUIT as Q
S = F.use_store("t/meaning.json", clean=True)
sys.path.insert(0, F.DEV)
import fw_meaning as FM
from fw_picker import Picker, blocks_inside, fuse

SEA, S1, S2, DOG, D1, BOAT, B1 = ("20261001T100000-a000", "20261001T100000-a001", "20261001T100000-a002",
                                  "20261002T100000-b000", "20261002T100000-b001", "20261003T100000-c000", "20261003T100000-c001")
F.write_store([blk(SEA, [S1, S2], "harbor notes"), blk(S1, "gulls over the pier"), blk(S2, "the tide went out slowly"),
               blk(DOG, [D1], "dog walk"), blk(D1, "loneliness at night, the ferry horn"),
               blk(BOAT, [B1], "loneliness list"), blk(B1, "things to buy")], [SEA, DOG, BOAT], version=9)
S.cmd_migrate(None)

# --- pure: fusing ranks, the answer read, the Picker mixing it in
same("fuse: by reciprocal rank, something in both lists first", fuse(["a", "b", "c"], ["c", "x"]), ["c", "a", "b", "x"])
same("ids_of: the answer's block ids, in order, once each", FM.ids_of({"results": [["a", 0.9], ["b", 0.8], ["a", 0.7]]}), ["a", "b"])
lib = S.build_library(S.load_data())
refs = [BOAT, DOG, SEA]
p = Picker(lib, refs, inside=blocks_inside(lib, refs))
p.query = "loneliness"
before = [r[1] for r in p.rows()]
check("typed: the title matches", before and before[0] == "loneliness list", before)
p.meaning = ("loneliness", [D1, S2])
rows = [r[1] for r in p.rows()]
check("  with the search service's answer: a block found by meaning listed under its pericope, said so",
      "  · loneliness at night, the ferry horn" in rows or any("(by meaning)" in r and "ferry" in r for r in rows), rows)
check("  a pericope only the service found joins the list", any(r.startswith("harbor notes") for r in rows), rows)
p.meaning = ("lonely", [S2])
same("  an answer to another query isn't used", [r[1] for r in p.rows()], before)

# --- the Asker: asks once the typing pauses, gives the answer back for the query still wanted
asked = []
class Mini(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)["q"][0]
        asked.append(q)
        body = json.dumps({"model": "fake", "results": [[S2, 0.71], [D1, 0.69]] if "sea" in q else [[D1, 0.8]]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass
server = http.server.HTTPServer(("127.0.0.1", 0), Mini)
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{server.server_address[1]}"
now = [0.0]
a = FM.Asker(URL, clock=lambda: now[0])
a.want("se"); now[0] = 1; a.tick()
a.want("sea"); a.tick()
check("Asker: not asked while you type, nor under three letters", asked == [], asked)
now[0] = 2; a.tick()
F.wait_for(lambda: asked == ["sea"])
got = None
F.wait_for(lambda: (got := a.tick()) is not None and globals().update(got_=got) is None)
same("  asked once the typing pauses; the answer, for the query still wanted", globals().get("got_"), ("sea", [S2, D1]))
dead = FM.Asker("http://127.0.0.1:9", clock=lambda: now[0])
dead.want("anything"); now[0] = 10; dead.tick()
F.wait_for(lambda: dead.resting > 0)
check("  no service: nothing comes, and it rests a while before asking again", dead.tick() is None and dead.resting >= 10 + FM.RESTING - 1)
check("  off: never asked", not FM.Asker("off").on() and not FM.Asker("").on())

# --- in fw: home's search, then Quote a block, with the fake service
t = F.fw("open", rows=30, env={"FW_MEANING_URL": URL})
t.key(*"sea and")
check("home: the search service's answer comes in after a pause, a block found by meaning under its pericope",
      t.until(lambda: "the tide went out slowly  (by meaning)" in t.text()), t.text())
t.key(ESC); t.done()

t = F.fw("loneliness list", rows=30, env={"FW_MEANING_URL": URL})
t.key(F.END, ENTER, "/", "quote", ENTER, *"sea gulls")
check("Quote a block: the same", t.until(lambda: "(by meaning)" in t.text()), t.text())
t.key(ESC, ESC, Q, ESC); t.done()
server.shutdown()

F.report("MEANING")
