# an image block: a picture file dropped on the terminal (its path pasted) becomes one
import functools, http.server, os, struct, sys, threading, zlib
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk, UP, BS, QUIT as Q, UNDO as Z, REDO as Y
S = F.use_store("t/image.json", clean=True)
HOST, H1, X, QH, QQ = "20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-c000", "20261001T100000-c001"
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"
ESCAPE = b"\x1b]1337;File=inline=1"

def png(path, w, h):
    """A plain grey picture, w × h pixels."""
    chunk = lambda kind, data: struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))

os.makedirs("t/pics dir", exist_ok=True)
PIC = os.path.abspath("t/pics dir/wide pic.png")
png(PIC, 40, 20)
F.write_store([blk(HOST, [H1, X], "host"), blk(H1, "hello world"), blk(X, "end"),
               blk(QH, [QQ], "qhost"), blk(QQ, {"quote": HOST})], [HOST, QH], version=9)
S.cmd_migrate(None)
same("the store migrates to the current schema, nothing in it changed", S.load_data()["schemaVersion"], S.SCHEMA_VERSION)

def B(): return S.index(S.load_data())
def kids(i, b=None):
    b = b or B()
    return [("image", S.image_of(b[k])) if S.image_of(b[k]) else b[k]["content"] for k in S.children(b[i])]
RAW = []   # everything the terminal's been sent (pyte drops the picture escapes)
feed = F.pyte.ByteStream.feed
F.pyte.ByteStream.feed = lambda self, data: (RAW.append(data), feed(self, data))
def open_(title, pictures="1"):
    RAW.clear()
    t = F.fw(title, rows=30, cols=60, env={"FW_PICTURES": pictures})
    t.raw = RAW
    return t
def drop(t, path):
    t.key(PASTE_START + path.replace(" ", "\\ ") + PASTE_END)
    t.settle()

t = open_("host")   # at the end of "end"
t.key(UP, F.END)     # to the end of "hello world"
drop(t, PIC)
b = B()
name = kids(HOST, b)[1][1] if len(kids(HOST, b)) > 1 and isinstance(kids(HOST, b)[1], tuple) else None
same("a dropped picture's path (spaces escaped) makes an image block where the cursor was", kids(HOST, b),
     ["hello world", ("image", name), "end"])
check("  its file is copied into the images folder beside the store, named by its bytes",
      name and os.path.exists(os.path.join("t/images", name)) and name.endswith(".png"), name)
rows = t.text().split("\n")
top = next((y for y, r in enumerate(rows) if "hello world" in r), 0) + 2
check("  drawn in a box of its own, blank inside for the picture (40×20 px at 49 columns: 12 rows), then the next block",
      rows[top][2:3] == "┌" and all(rows[y].strip("│ ") == "" for y in range(top + 1, top + 13))
      and rows[top + 13][2:3] == "└" and "end" in rows[top + 15], "\n".join(rows))
check("  and the picture is drawn there: iTerm's inline image escape", any(ESCAPE in r for r in t.raw))
t.key(Z); t.settle()
same("^Z takes it back out", kids(HOST), ["hello world", "end"])
t.key(Y); t.settle()
same("^Y puts it back", kids(HOST), ["hello world", ("image", name), "end"])
t.key(PASTE_START + "words" + PASTE_END); t.settle()
check("a paste that isn't a picture's path is typed, as ever", any("words" in str(k) for k in kids(HOST)), kids(HOST))
t.key(Z); t.settle()
t.key(Q, F.ESC); t.done()

t = open_("host")
same("reopened: still there", kids(HOST), ["hello world", ("image", name), "end"])
check("  and drawn again", any(ESCAPE in r for r in t.raw))
t.key(UP)   # from "end": the image, selected whole
t.key(BS); t.settle()
same("Backspace on it (selected whole) removes it", kids(HOST), ["hello world", "end"])
t.key(Z); t.settle()
same("  ^Z brings it back", kids(HOST), ["hello world", ("image", name), "end"])
t.key(Q, F.ESC); t.done()

t = open_("qhost")
check("a quote of the entry shows the picture too", any(ESCAPE in r for r in t.raw))
t.key(Q, F.ESC); t.done()

t = open_("host", pictures="0")
check("a terminal that can't draw pictures gets a line saying what's there", "▣ picture 40×20" in t.text(), t.text())
t.key(Q, F.ESC); t.done()

t = open_("host")
t.key(UP, F.HOME)
drop(t, os.path.abspath("t/nope.png"))
check("a path to a file that isn't there is just typed", any("nope.png" in str(k) for k in kids(HOST)), kids(HOST))
t.key(Q, F.ESC); t.done()

IMG = "20261001T100000-b003"
def reset(image=None):
    """The store as it began (with picture file `image` in, between the two blocks)."""
    F.write_store([blk(HOST, [H1, IMG, X] if image else [H1, X], "host"), blk(H1, "hello world"), blk(X, "end"),
                   blk(QH, [QQ], "qhost"), blk(QQ, {"quote": HOST})] + ([blk(IMG, {"image": image})] if image else []),
                  [HOST, QH], version=9)
    S.cmd_migrate(None)

# drawing: only what changed, never the whole screen
CLEAR = b"\x1b[2J"
reset(name)
t = open_("host")
F.wait_for(lambda: any(ESCAPE in r for r in t.raw))
RAW.clear()
t.key(F.END, "!"); t.settle()   # typing below the picture: it hasn't moved
check("typing below a picture doesn't send it again, nor clear the screen",
      not any(ESCAPE in r or CLEAR in r for r in t.raw))
t.key(Q, F.ESC); t.done()
t = open_("host")
F.wait_for(lambda: any(ESCAPE in r for r in t.raw))
RAW.clear()
t.key(UP, UP, F.HOME, F.ENTER); t.settle()   # a block above it: it moves down a row
check("a block above it moves it: it's sent again, where it is now", sum(r.count(ESCAPE) for r in t.raw) == 1, t.raw)
check("  without clearing the screen", not any(CLEAR in r for r in t.raw))
t.key(Z); t.settle()
t.key(Q, F.ESC); t.done()

reset()
BIG = os.path.abspath("t/pics dir/big.png")
png(BIG, 3000, 1500)
t = open_("host")
t.key(UP, F.END)
drop(t, BIG)
F.wait_for(lambda: any(ESCAPE in r for r in t.raw))
thumbs = os.listdir("t/.fw-thumbs") if os.path.isdir("t/.fw-thumbs") else []
check("a big picture's drawn from a smaller copy, kept beside the store", any(n.endswith("-800.jpg") for n in thumbs), thumbs)
sent = max((len(r) for r in t.raw if ESCAPE in r), default=0)
check("  so less is sent", 0 < sent < os.path.getsize(BIG), (sent, os.path.getsize(BIG)))
t.key(Z); t.settle()
t.key(Q, F.ESC); t.done()

# / → Add a picture from a link: downloaded into the store
os.makedirs("t/web", exist_ok=True)
png("t/web/pic.png", 30, 30)
open("t/web/page.html", "w").write("<html>not a picture</html>")
web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(
    type("Quiet", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory="t/web"))
threading.Thread(target=web.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{web.server_port}"
reset()
t = open_("host")
t.key(UP, F.END, F.ENTER, "/")
check("on an empty line, / offers a picture from a link", "Add a picture from a link" in t.text(), t.text())
t.key("pic", F.ENTER)
check("  which asks for its address", "picture ›" in t.text(), t.text())
t.key(PASTE_START + URL + "/page.html" + PASTE_END, F.ENTER)
check("  a page that isn't a picture: it says so, and waits for another",
      t.until(lambda: "not a png" in t.text()) and "picture ›" in t.text(), t.text())
t.key(*[BS] * len("/page.html"), "/pic.png", F.ENTER)
web_name = None
def got():
    global web_name
    k = kids(HOST)
    web_name = next((x[1] for x in k if isinstance(x, tuple)), None)
    return web_name
check("  a picture's address: downloaded, and an image block where the cursor was", t.until(got), kids(HOST))
same("  in its place", kids(HOST), ["hello world", ("image", web_name), "end"])
check("  its file kept in the images folder, not the link",
      web_name and open(os.path.join("t/images", web_name), "rb").read() == open("t/web/pic.png", "rb").read()
      and URL not in open(S.DATA_PATH).read())
t.key(Z); t.settle()
same("  ^Z takes it back out", kids(HOST), ["hello world", "end"])
t.key(Q, F.ESC); t.done()
web.shutdown()

# an image is a block like any other: turned into a quote, quoted, opened
def blocks_of(ref):
    b = B()
    return {k: b[k]["content"] for k in S.children(b[ref])}
reset(name)
t = open_("host")
t.key(UP)   # the image, selected whole
t.key(F.MENU, "turn into a quote", F.ENTER); t.settle()
k = kids(HOST)
popped = k[1].get("quote") if len(k) == 3 and isinstance(k[1], dict) else None
check("Turn into a quote, on an image: it moves to an entry of its own, quoted where it was",
      popped and k[0] == "hello world" and k[2] == "end" and B()[IMG]["content"] == {"quote": popped}, k)
check("  the new entry holds the picture", popped and kids(popped) == [("image", name)], popped and kids(popped))
check("  titled from it", popped and S.build_library(S.load_data())[popped]["title"] == "picture")
check("  and it's still drawn, in the quote", t.until(lambda: any(ESCAPE in r for r in t.raw[-5:])))
t.key(Z); t.settle()
same("  ^Z: back as it was", kids(HOST), ["hello world", ("image", name), "end"])
check("  the entry gone", popped not in B())
t.key(UP, F.MENU, "and open it", F.ENTER); t.settle()
check("Turn into a quote and open it, on an image: in the new entry", t.until(lambda: "host ›" in t.text()), t.text())
t.key(Q); t.settle()
t.key(Z); t.settle()
t.key(Q, F.ESC); t.done()

reset(name)
t = open_("qhost")
t.key(F.END, F.ENTER, "/", "quote", F.ENTER, "picture")
check("Quote a block finds a picture inside an entry, by its title", "· picture" in t.text(), t.text())
t.key(F.DOWN)   # from the entry it's in (the first result) to it
rows = t.text()
t.key(F.ENTER); t.settle()
k = kids(QH)
made = [x["quote"] for x in k if isinstance(x, dict) and x.get("quote") not in (None, HOST)]
pic = S.children(B()[made[0]])[0] if made else None
check("  Enter: the picture is an entry of its own, quoted here, showing the picture alone",
      made and B()[made[0]].get("entry") and B()[pic]["content"] == {"image": name}
      and t.until(lambda: any(ESCAPE in r for r in t.raw[-5:])), (k, rows))
check("  and quoted where it was", {"quote": made[0]} in kids(HOST) if made else False, kids(HOST))
t.key(UP, DOWN := "\x1b[B", DOWN, "x"); t.settle()
check("  a quote of a picture can't be gone into: arrows and typing leave the picture as it is",
      pic and B()[pic]["content"] == {"image": name}, pic and B()[pic]["content"])
t.key(Z); t.settle()
t.key(UP, F.MENU, "open it", F.ENTER); t.settle()
check("  Open it on that quote: the entry the picture's in", t.until(lambda: "qhost ›" in t.text()), t.text())
t.key(Q); t.settle()
t.key(Q, F.ESC); t.done()

F.report("IMAGE")
