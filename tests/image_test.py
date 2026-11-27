# pictures: a picture is a pericope of its own ({image: file}, the file kept in images/ beside the store, named by its
# bytes), quoted where it's put; one held in a block is taken out on the next write; downloaded from a link, never linked
import functools, http.server, json, os, sys, threading
sys.path.insert(0, "."); import fwtest as F
from fwtest import check, same, blk
S = F.use_store("image")
HOST, H1, X, IMG, QH, QQ = ("20261001T100000-b000", "20261001T100000-b001", "20261001T100000-b002", "20261001T100000-b003",
                            "20261001T100000-c000", "20261001T100000-c001")
os.makedirs("t/pics dir", exist_ok=True)
F.png("t/pics dir/wide pic.png", 40, 20)
name = S.add_image(os.path.abspath("t/pics dir/wide pic.png"))
check("add_image: copied into the images folder beside the store, named by its bytes", name.endswith(".png")
      and open(S.image_file(name), "rb").read() == open("t/pics dir/wide pic.png", "rb").read(), name)
same("  the same picture again: kept once", S.add_image_data(F.png(None, 40, 20), "again"), name)
check("  not a picture: refused", "not a png" in (F.refused(S.add_image_data, b"<html>", "page.html") or ""))
check("  a file that isn't there: refused", F.refused(S.add_image, "t/nope.png"))

def fresh(image=None):
    F.store(blk(HOST, [H1, IMG, X] if image else [H1, X], "host", entry=True), blk(H1, "hello world"), blk(X, "end"),
            blk(QH, [QQ], "qhost", entry=True), blk(QQ, {"quote": HOST}), *([blk(IMG, {"image": image})] if image else []))
fresh(name)
b = F.blocks()
qid = S.children(b[HOST])[1]
same("a picture held in a block: taken out on the next write, quoted where it was", F.kids(HOST), ["hello world", ("quote", IMG), "end"])
check("  the picture a pericope now, its id kept", b[IMG].get("entry") and b[IMG]["content"] == {"image": name}, b[IMG])
same("  its quote's id from the picture's and the holder's: the same on every machine", qid, S.picture_quote_id(IMG, HOST))
same("titled \"picture\" with no model title", S.build_library(S.load_data())[IMG]["title"], "picture")
json.dump({"model": "test", "titles": {name: "Grey square at noon"}}, open("t/picture-titles.json", "w"))
same("  with one from the other machine (picture-titles.json), that", S.build_library(S.load_data())[IMG]["title"], "Grey square at noon")
from fw.search import Search, blocks_inside
lib = S.build_library(S.load_data())
refs = [r for r, e in lib.items() if e["entry"]]
p = Search(lib, refs, inside=blocks_inside(lib, refs)); p.query = "grey square"
check("  found by it, a pericope of its own, and the place that quotes it", [r[1] for r in p.rows()][:2] == ["Grey square at noon", "  “Grey square at noon” quoted in host"], p.rows())
os.remove("t/picture-titles.json")
check("a picture block is whole (nothing to write in)", S.is_whole(F.blocks()[IMG]))
check("  it can't be popped out again (it's a pericope already: a quote of it is)", F.refused(S.pop_out, qid))
same("block_type: image", S.block_type(F.blocks()[IMG]), "image")

# a picture from a link: downloaded into the store
os.makedirs("t/web", exist_ok=True)
F.png("t/web/pic.png", 30, 30)
open("t/web/page.html", "w").write("<html>not a picture</html>")
web = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(
    type("Quiet", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None}), directory="t/web"))
threading.Thread(target=web.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{web.server_port}"
same("fetch_image: the bytes at the address", S.fetch_image(URL + "/pic.png"), open("t/web/pic.png", "rb").read())
check("  a page that isn't a picture: refused when kept", "not a png" in (F.refused(S.add_image_data, S.fetch_image(URL + "/page.html"), "page") or ""))
check("  not there: refused", "404" in (F.refused(S.fetch_image, URL + "/nope.png") or ""))
check("  not a web address: refused", "web address" in (F.refused(S.fetch_image, "file:///etc/passwd") or ""))
web.shutdown()
F.report()
