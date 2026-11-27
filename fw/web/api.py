"""The API, a table of (method, path pattern) -> handler. A handler takes the request (server.Handler: `ask(name)`,
`body()`, `groups`) and returns (status, JSON), or None when it answered itself (a file, the live stream)."""
from __future__ import annotations

import json
import os
import re

from fw import store
from fw.web import current, live, visits
from fw.web.common import ID, IMAGE_RE, blocks_of, library
from fw.web.header import pericope_json
from fw.web.lists import ask_meaning, exits_json, home_json, kinds_json, search_json
from fw.web.snapshot import snapshot_json, snapshot_part
from fw.web.views import mask_op, masking_json, node_json, quote_json


def keys_path():
    """The user's key bindings for the web editor (#/keys), beside the store."""
    return store.DATA_PATH.with_name("web-keys.json")


def strings(d) -> dict:
    return {k: v for k, v in d.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(d, dict) else {}


def read_keys() -> dict:
    try:
        return strings(json.loads(keys_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def write_keys(keys: dict) -> None:
    tmp = keys_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, keys_path())


def ids_arg(r) -> list:
    return [i for i in r.ask("ids").split(",") if i]


def new_pericope(content, title=None) -> dict:
    """A new pericope holding `content`: its id and base (home's waiting pericope saves into it at once)."""
    def make(data, blocks):
        return store.add_block(data, blocks, store.new_id(blocks), content, title=title, entry=True)["id"]
    ref = store.transact(store.editing(make), tidy=False)
    return {"id": ref, "base": store.content_hash(blocks_of(library()), ref)}


# --- reading

def get_version(r):
    return 200, {"code": current.CODE, "page": current.page_stamp(), "store": str(store.DATA_PATH)}


def get_home(r):
    lib = library()
    return 200, {"count": sum(1 for e in lib.values() if e["entry"]), "rows": home_json(lib)}


def get_search(r):
    q = r.ask("q")
    meaning = ask_meaning(q) if r.ask("meaning", "0") == "1" else None
    return 200, {"query": q, "rows": search_json(library(), q, meaning), "meaning": meaning is not None}


def get_exits(r):
    lib, here = library(), r.groups[0]
    if not (lib.get(here) or {}).get("entry"):
        return 404, {"error": "no such pericope"}
    return 200, {"rows": exits_json(lib, here, r.ask("meaning", "0") == "1")}


def get_masking(r):
    lib, qid = library(), r.ask("quote")
    if not store.quoted((lib.get(qid) or {}).get("block")):
        return 404, {"error": "no such quote"}
    return 200, masking_json(lib, qid)


def get_blocks(r):
    lib = library()
    return 200, {"blocks": [node_json(lib, i) for i in ids_arg(r) if i in lib]}


def get_snapshot(r):
    ids = set(ids_arg(r))
    return 200, snapshot_part(library(), ids) if ids else snapshot_json(library())


def get_quote(r):
    """A new quote of `target` as the page draws it, going `into` (the blocks around it) at `depth`: never refused,
    drawn ⋯ past the depth and ↻ at a loop."""
    data, version = store.load_versioned()
    lib = store.build_library(data)
    if (target := r.ask("target")) not in lib:
        return 404, {"error": "no such block"}
    here = tuple(i for i in r.ask("into").split(",") if i in lib)
    return 200, {**quote_json(lib, None, target, None, [], {}, int(r.ask("depth", "0") or 0) + 1, here), "version": version}


def get_pericope(r):
    data, version = store.load_versioned()
    lib = store.build_library(data)
    if r.groups[0] not in lib:
        return 404, {"error": "no such pericope"}
    return 200, {**pericope_json(lib, r.groups[0]), "version": version}


def get_image(r):
    name = r.groups[0]
    return r.file(store.IMAGES_PATH / name) if IMAGE_RE.match(name) else (404, {"error": "no such picture"})


# --- writing

def put_keys(r):
    write_keys(strings(r.body().get("keys") or {}))
    return 200, {"keys": read_keys()}


def put_lens(r):
    body = r.body()
    hashes, _ = store.commit_view(r.groups[0], body.get("text") or "", None, base=body.get("base"), at=body.get("version"))
    return 200, {"bases": hashes, "version": store.written_version()}


def put_pericope(r):
    """{draft, title, base, final, version, also}: saved (store.commit); `also`: ids whose new base comes back,
    unless the save merged (the store then holds more than they've seen)."""
    body, ref = r.body(), r.groups[0]
    fields = [{"key": "title", "value": body.get("title") or "", "editable": True}] if "title" in body else []
    notes, base, _, _ = store.commit(ref, body.get("draft"), fields, final=bool(body.get("final")),
                                     base=body.get("base"), at=body.get("version"))
    version = store.written_version()
    blocks = blocks_of(library())
    merged = bool(body.get("version")) and version != store.current_version()
    also = {} if merged else {i: store.content_hash(blocks, i) for i in body.get("also") or [] if i in blocks}
    return 200, {"base": base, "notes": notes, "gone": ref not in blocks, "bases": also, "version": version}


def post_visit(r):
    body = r.body()
    ago = body.get("ago") or 0
    at = store.clock() - (ago if isinstance(ago, (int, float)) and 0 <= ago <= store.VISIT_GAP else 0)
    lib = library()
    pericope = body.get("pericope") if (lib.get(body.get("pericope")) or {}).get("entry") else None
    visits.attention(blocks_of(lib), pericope, body.get("block"), "".join(f for f in "cwq" if f in str(body.get("flags") or "")), at)
    visits.flush_visits(everything=bool(body.get("flush")))
    return 200, {}


def post_pericope(r):
    return 200, new_pericope([], (r.body().get("title") or "").strip() or None)


def post_picture(r):
    """A picture pericope: the picture's own bytes (dropped), or {url} downloaded."""
    if (r.headers.get("Content-Type") or "").startswith("image/"):
        name = store.add_image_data(r.rfile.read(int(r.headers.get("Content-Length") or 0)), r.headers.get("X-Name") or "a dropped picture")
    else:
        url = (r.body().get("url") or "").strip()
        name = store.add_image_data(store.fetch_image(url), url)
    return 200, new_pericope({"image": name})


def post_clip(r):
    """{ids, cut, text}: blocks clipped (a cut one kept by the store while the clip holds it, store.clip_holds). A
    quote keeps its content: pasted, it quotes what it quotes."""
    body = r.body()
    blocks = blocks_of(library())
    ids = [i for i in body.get("ids") or [] if i in blocks]
    units = [{"id": i, **({"quote": blocks[i]["content"]} if store.quoted(blocks[i]) else {})} for i in ids]
    store.save_clip({"text": body.get("text") or "", "blocks": units, **({"cut": True} if body.get("cut") else {})} if ids else None)
    return 200, {"ok": True}


def post_maskop(r):
    body = r.body()
    return 200, {"mask": mask_op(body["draft"], body["mask"], body["op"], *(int(body.get(k) or 0) for k in "abi"))}


def post_maskto(r):
    body = r.body()
    store.mask_quote_to(body.get("quote"), body.get("block"))
    lib = library()
    return 200, node_json(lib, body.get("quote")) if body.get("quote") in lib else {}


def post_popout(r):
    return 200, {"id": store.pop_out(r.body().get("block"))[0]}


def post_restore(r):
    return 200, {"record": store.restore(r.body().get("record") or {"blocks": {}})}


def act_link(b):
    to, rec = store.link_text(b.get("block"), b.get("text") or "", b.get("at"), b.get("to"), b.get("title"))
    return {"to": to, "title": library()[to]["title"], "record": rec}


def act_popout(b):
    entry, _, rec = store.pop_out(b.get("block"))
    return {"id": entry, "record": rec}


def act_kind(b):
    kid, rec = store.set_kind(b.get("block"), b.get("kind"), b.get("answer"), b.get("name") or "")
    return {"kind": kid, "record": rec}


def act_newkind(b):
    kid, rec = store.new_kind(b.get("name") or "")
    return {"kind": kid, "record": rec}


def act_paraphrase_it(b):
    pid, rec = store.paraphrase_it(b.get("block"))
    return {"id": pid, "record": rec}


ACTS = {   # the page's block actions, each a store function; its undo record comes back
    "detach": lambda b: {"record": store.detach(b.get("quote"))[2]},
    "popout": act_popout,
    "setmask": lambda b: {"record": store.set_quote_mask(b.get("quote"), b.get("draft"), b.get("mask"))[1]},
    "showall": lambda b: {"record": store.set_quote_mask(b.get("quote"), None, None, inner=True)[1]},
    "show": lambda b: {"record": store.set_quote_show(b.get("quote"), list(b.get("show") or []))[1]},
    "lock": lambda b: {"record": store.set_quote_lock(b.get("quote"), bool(b.get("on")))[1]},
    "link": act_link,
    "unlink": lambda b: {"record": store.unlink_text(b.get("block"), b.get("to"), b.get("at"))},
    "kind": act_kind,
    "newkind": act_newkind,
    "rename": lambda b: {"record": store.rename_kind(b.get("kind"), b.get("name") or "")},
    "paraphrase_it": act_paraphrase_it,
    "paraphrase": lambda b: {"record": store.set_paraphrase(b.get("block"), b.get("source"))},
    "delete": lambda b: {"quotes": store.delete_entry(b.get("pericope"))},
}


def post_act(r):
    body = r.body()
    act = ACTS.get(body.get("do"))
    return (200, act(body)) if act else (404, {"error": f"no action {body.get('do')!r}"})


def ok(body):
    return lambda r: (200, body())


ROUTES = [(method, re.compile(pattern), fn) for method, pattern, fn in [
    ("GET", r"/|/index\.html", lambda r: r.file(current.WEB / "index.html")),
    ("GET", r"/dist/(.*)", lambda r: r.file(current.WEB / "dist" / os.path.basename(r.groups[0]))),
    ("GET", r"/images/(.*)", get_image),
    ("GET", r"/api/stamp", ok(lambda: {"stamp": live.stamp()})),
    ("GET", r"/api/live", lambda r: r.live()),
    ("GET", r"/api/keys", ok(lambda: {"keys": read_keys()})),
    ("GET", r"/api/version", get_version),
    ("GET", r"/api/home", get_home),
    ("GET", r"/api/search", get_search),
    ("GET", rf"/api/exits/({ID})", get_exits),
    ("GET", r"/api/masking", get_masking),
    ("GET", r"/api/clip", ok(lambda: store.load_clip() or {})),
    ("GET", r"/api/blocks", get_blocks),
    ("GET", r"/api/snapshot", get_snapshot),
    ("GET", r"/api/kinds", lambda r: (200, kinds_json(library(), r.ask("members", "0") == "1"))),
    ("GET", r"/api/quote", get_quote),
    ("GET", rf"/api/pericope/({ID})", get_pericope),
    ("PUT", r"/api/keys", put_keys),
    ("PUT", rf"/api/lens/({ID})", put_lens),
    ("PUT", rf"/api/pericope/({ID})", put_pericope),
    ("POST", r"/api/visit", post_visit),
    ("POST", r"/api/pericope", post_pericope),
    ("POST", r"/api/popout", post_popout),
    ("POST", r"/api/act", post_act),
    ("POST", r"/api/clip", post_clip),
    ("POST", r"/api/maskop", post_maskop),
    ("POST", r"/api/restore", post_restore),
    ("POST", r"/api/maskto", post_maskto),
    ("POST", r"/api/picture", post_picture),
]]


def route(method: str, path: str):
    """The handler for a request and its path's groups, or (None, ())."""
    for m, pattern, fn in ROUTES:
        if m == method and (found := pattern.fullmatch(path)):
            return fn, found.groups()
    return None, ()
