"""fw_web — the core of fw's web editor (2026-11-17): a local server over the store.

    fw web                 start it (if it isn't running) and open the browser
    python3 fw_web.py [--port 8020] [--no-open]

The editor is a page (web/: ProseMirror, built into web/dist/); this is
everything else, and the only part that touches the store. It goes through
fw_store's own functions, so every rule the terminal editor keeps is kept
here too: a save is the same `commit` of a draft in fw's draft format
(marker lines, fw_draft), refused over a change made elsewhere (`base`),
tidied, validated. The data model stays apart from the editor: the page
sees JSON, never the store.

Standard library only (and loro, through fw_store). Listens on 127.0.0.1.

    GET  /                          the page
    GET  /api/home                  the pericopes in the garden's order
    GET  /api/search?q=&meaning=1   home's search (fw_picker.Picker's rows); with
                                    meaning=1, the search service asked too (fw_meaning) and mixed in
    GET  /api/pericope/<id>         a pericope: its header and its blocks, as a tree
    PUT  /api/pericope/<id>         {draft, title, base, final, also}: saved (store.commit), any block (a
                                    quote's target too); `also`: ids whose new base comes back (the editors
                                    around a quote written through, whose shown text changed)
    PUT  /api/lens/<quote id>       {text, base}: a masked quote's view written through (store.commit_view)
    POST /api/pericope              {title}: a new pericope, {id, base}
    GET  /api/quote?target=         a new quote of a block, as the page draws it
    POST /api/popout                {block}: a pericope of its own, quoted where it was (store.pop_out)
    POST /api/maskto                {quote, block}: the quote masked to just that block
    POST /api/picture               {url}, or a picture's bytes: a picture pericope (store.add_image_data)
    POST /api/act                   {do, …}: the Ctrl+/ menu's actions (detach, popout, showall, show, lock,
                                    link, unlink, kind, rename, paraphrase_it, paraphrase, delete), each a
                                    store function; its undo record
                                    comes back
    GET  /api/kinds                 every kind, {id, name} (the kinds picker)
    GET  /api/clip                  what fw last clipped (the rich clipboard, .fw-clip.json, shared with the terminal)
    POST /api/clip                  {ids, cut, text}: blocks clipped (a cut one kept by the store while it's held)
    GET  /api/blocks?ids=           blocks as the page edits them, keeping their ids (pasted after a cut: moved)
    POST /api/restore               {record}: an action taken back (store.restore); its inverse comes back
    GET  /api/masking?quote=        what masking a quote works on: its target's draft, the mask, the lines
    POST /api/maskop                {draft, mask, op, a, b, i}: one key while masking, the mask back
    GET  /api/stamp                 when the store last changed (the page follows it)
    GET  /api/keys, PUT /api/keys   the user's key bindings for the web editor (web-keys.json beside the store)
    GET  /images/<file>             a picture
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw_meaning  # noqa: E402
import fw_store as store  # noqa: E402
from fw_picker import NEW, Picker, blocks_inside  # noqa: E402

WEB = HERE / "web"
PORT = 8020


def code_stamp() -> str:
    """Which code this is: the fw_*.py beside it, by name, size and time (`fw web` starts the core again when the
    one running is older than the code)."""
    import hashlib
    files = sorted(HERE.glob("fw_*.py"))
    return hashlib.sha1("".join(f"{f.name}:{f.stat().st_size}:{f.stat().st_mtime_ns};" for f in files).encode()).hexdigest()[:12]


CODE = code_stamp()   # (as it was when this one started)


def page_stamp() -> str:
    """Which page is built (web/dist, by name, size and time): the page reloads itself when it changes."""
    import hashlib
    files = sorted((WEB / "dist").glob("*"))
    return hashlib.sha1("".join(f"{f.name}:{f.stat().st_size}:{f.stat().st_mtime_ns};" for f in files if f.is_file()).encode()).hexdigest()[:12]


def page_stale() -> bool:
    """The page's source (web/src, its build script and config) changed since it was last built."""
    built = WEB / "dist" / "app.js"
    if not built.exists():
        return True
    sources = [*(WEB / "src").glob("*"), WEB / "build.mjs", WEB / "tailwind.config.js", WEB / "index.html"]
    return max((f.stat().st_mtime for f in sources if f.exists()), default=0) > built.stat().st_mtime


def build_page() -> bool:
    """`npm run build`'s build (node build.mjs), with whichever node there is (on PATH, else fnm's). Whether it built."""
    import shutil
    import subprocess
    node = shutil.which("node")
    cmd = [node, "build.mjs"] if node else (["fnm", "exec", "--using=default", "node", "build.mjs"] if shutil.which("fnm") else None)
    if not cmd:
        return False
    return subprocess.run(cmd, cwd=WEB, capture_output=True, timeout=120).returncode == 0


ACTIVE = [0]   # requests being answered now (a restart waits for none)


def keys_path() -> Path:
    """The user's own key bindings for the web editor (#/keys): beside the store, not in it."""
    return store.DATA_PATH.with_name("web-keys.json")


def read_keys() -> dict:
    try:
        got = json.loads(keys_path().read_text(encoding="utf-8"))
        return {k: v for k, v in got.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def write_keys(keys: dict) -> None:
    tmp = keys_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(keys, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, keys_path())


def keep_current() -> None:
    """Always the latest code (the user, 2026-11-18): every second, the page built again when its source changed,
    and this core started again, in place, when fw's code changed (once no request is being answered, so no save
    is cut off). The page sees both (/api/version) and reloads itself. Off in the tests ($FW_WEB_WATCH=0)."""
    import time
    while True:
        time.sleep(1)
        try:
            if page_stale():
                build_page()
            if code_stamp() != CODE and ACTIVE[0] == 0:
                print("fw web: fw's code changed; starting again", file=sys.stderr, flush=True)
                os.execv(sys.executable, [sys.executable, *sys.argv])
        except (OSError, ValueError):
            continue
ID_RE = re.compile(r"^\d{8}T\d{6}-[0-9a-f]{4}$")
IMAGE_RE = re.compile(r"^[0-9a-f]+\.(png|jpg|jpeg|gif|webp)$")
MAX_DEPTH = store.MAX_DEPTH  # quotes inside quotes shown this deep, then a stand-in


# --- pure: the store as the page sees it -----------------------------------------

def blocks_of(library: dict) -> dict:
    return {i: e["block"] for i, e in library.items()}


def shown_text(text: str) -> str:
    """A masked view's text as the page shows it: each hidden stretch a …."""
    return text.replace(store.ELLIPSIS, "…").replace(store.CLOSE, "").replace(store.OPEN, "")


def items_json(library: dict, items: list, depth: int, path: tuple) -> list:
    """A quote's body (fw_block.quote_items' items) as the page draws it, read only."""
    out = []
    for item in items:
        match item:
            case ("text", text):
                out.append({"t": "text", "text": shown_text(text)})
            case ("image", iid):
                out.append({"t": "image", "file": store.image_of(library.get(iid, {}).get("block"))})
            case ("quote", target, mask, show, inner):
                out.append(quote_json(library, None, target, mask, show, inner, depth + 1, path))
    return out


def editable(library: dict, target: str, mask, depth: int, path: tuple, locked: bool) -> bool:
    """Whether a quote of `target` can be written through here: unmasked
    (a masked one through the lens: not yet), not locked (nor inside a locked
    one: fw_block.locked_by's cascade), not a loop, not past MAX_DEPTH, and
    not a picture (nothing to write in)."""
    entry = library.get(target)
    return (entry is not None and mask is None and not locked and depth <= MAX_DEPTH and target not in path
            and not store.image_of(entry["block"]))


def tree_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> list:
    """What block `ref` holds, as the page edits it: its blocks (node_json);
    a block of text, its own text (`own`: saved as plain text, no marker);
    a picture, the picture."""
    blocks = blocks_of(library)
    b = blocks[ref]
    if isinstance(b.get("content"), str):
        return [{"t": "text", "id": ref, "own": True, "text": b["content"], "links": links_json(library, b), "para": para_json(library, b)}]
    if store.image_of(b):
        return [{"t": "image", "id": None, "file": store.image_of(b)}]
    return [node_json(library, k, depth, path, locked) for k in store.children(b)]


def kept_json(library: dict, line: str, depth: int, path: tuple) -> dict | None:
    """A quote or picture line of a draft (one the lens keeps as it is, or masking shows as one unit) as the page
    draws it, read only: a quote with what it shows (in full, as anywhere else), or the picture."""
    if (q := store.QUOTE_RE.fullmatch(line)):
        qid, target = q.group(2), q.group(1)
        blocks = blocks_of(library)
        data = node_json(library, qid, depth, path) if qid in blocks else quote_json(library, None, target, None, [], {}, depth, path)
        for k in ("tree", "lens", "base"):   # (read only here: written in where it lives)
            data.pop(k, None)
        return data
    if (m := store.IMAGE_RE.fullmatch(line)):
        return {"t": "image", "file": store.image_of(blocks_of(library).get(m.group(1)))}
    return None


def lens_json(library: dict, target: str, mask: list, depth: int = 1, path: tuple = ()) -> list:
    """A masked quote's view, as the page writes through it (the lens: fw_lens.view, put back by commit_view):
    segments in order: a block's text (`marker`, its marker line as the view has it, kept exactly; `text`, its
    shown lines, each hidden stretch the view's ELLIPSIS: a hole the page won't let go), or a line kept as
    it is (`line`: a quote or picture inside, drawn read only)."""
    blocks = blocks_of(library)
    out = []
    for line in store.view(store.block_draft(blocks, target), mask).split("\n"):
        if (m := store.BLOCK_RE.fullmatch(line)):
            out.append({"t": "text", "id": m.group(1), "marker": line, "lines": []})
        elif (q := store.QUOTE_RE.fullmatch(line)) or store.IMAGE_RE.fullmatch(line):
            title = (library.get(q.group(1)) or {}).get("title", "missing block") if q else "picture"
            out.append({"t": "line", "line": line, "title": title, "data": kept_json(library, line, depth + 1, path + (target,))})
        else:
            if not out or out[-1]["t"] != "text":
                out.append({"t": "text", "id": None, "marker": None, "lines": []})
            out[-1]["lines"].append(line)
    for seg in out:
        if seg["t"] == "text":
            seg["empty"] = not seg["lines"]
            seg["text"] = "\n".join(seg.pop("lines"))
    return out


def quote_json(library: dict, qid: str | None, target: str, mask, show, inner, depth: int, path: tuple,
               locked: bool = False) -> dict:
    """A quote of `target` (its own block `qid`, if it's one of the pericope's), with what it shows; and,
    when it can be written through (`editable`), what its target holds (`tree`) and its `base`."""
    blocks = blocks_of(library)
    entry = library.get(target)
    locked = locked or bool(qid and store.quote_lock(blocks.get(qid)))
    q = {"t": "quote", "id": qid, "target": target, "title": entry["title"] if entry else "missing block",
         "home": store.home_of(blocks, target)[0] if entry else None,
         "masked": mask is not None, "show": list(show or []),
         "lock": bool(qid and store.quote_lock(blocks.get(qid))), "locked": locked,
         "picture": bool(entry and store.image_of(entry["block"]))}
    if entry is None:
        q["body"] = [{"t": "note", "text": f"missing block {target}"}]
    elif target in path:
        q["body"] = [{"t": "note", "text": f"↻ {entry['title']}"}]
    elif depth > MAX_DEPTH:
        q["body"] = [{"t": "note", "text": f"⋯ {entry['title']}"}]
    else:
        items = store.quote_items(blocks, target, mask, frozenset(), inner)
        q["body"] = items_json(library, items, depth, path + (target,)) or [{"t": "note", "text": "(empty)"}]
        if editable(library, target, mask, depth, path, locked):
            q["tree"] = tree_json(library, target, depth + 1, path + (target,), locked)
            q["base"] = store.content_hash(blocks, target)
        elif mask is not None and qid and editable(library, target, None, depth, path, locked):   # masked: through the lens
            q["lens"] = lens_json(library, target, mask, depth, path)
            q["hole"] = store.ELLIPSIS
            q["base"] = store.content_hash(blocks, target)
    return q


def node_json(library: dict, ref: str, depth: int = 1, path: tuple = (), locked: bool = False) -> dict:
    """One block of a pericope, as the page edits it: text, a container of
    blocks, a quote (with what it shows, and what it holds when it can be
    written through), or a picture. `path`: the blocks quoted on the way
    here (a loop is drawn, not followed); `locked`: inside a locked quote."""
    blocks = blocks_of(library)
    b = blocks[ref]
    if store.quoted(b):
        target, _ = store.quoted(b)
        _, _, mask, show, inner = store.seen_quote(blocks, ref, {})
        return quote_json(library, ref, target, mask, show, inner, depth, path, locked)
    if store.image_of(b):
        return {"t": "image", "id": ref, "file": store.image_of(b)}
    kids = store.children(b)
    if kids:
        return {"t": "container", "id": ref, "children": [node_json(library, k, depth, path, locked) for k in kids],
                "para": para_json(library, b)}
    return {"t": "text", "id": ref, "text": store.own_text(blocks, ref), "links": links_json(library, b), "para": para_json(library, b)}


def para_json(library: dict, b: dict) -> dict | None:
    """What block `b` paraphrases, if it's marked: its id, title, where it lives, and its text (the dim guide
    an empty paraphrase shows, and Show its source)."""
    src = store.paraphrases(b)
    if not src:
        return None
    blocks = blocks_of(library)
    if src not in library:
        return {"id": src, "title": "(its source is gone)", "text": "", "home": None}
    return {"id": src, "title": library[src]["title"], "text": store.full_text(blocks, src)[:4000],
            "home": store.home_of(blocks, src)[0]}


def paraphrase_it(ref: str) -> tuple[str, dict]:
    """Paraphrase it (the terminal's): on quote `ref`, an empty paraphrase of what it quotes takes its place; on a
    block written here (or a picture), it moves to a pericope of its own (store.pop_out) and an empty paraphrase
    of that takes its place. Returns (the paraphrase's id, a record that undoes it all)."""
    b = store.index(store.load_data()).get(ref)
    if b is None:
        raise store.StoreError("write something first")
    record = None
    if store.quoted(b):
        source = store.quoted(b)[0]
    else:
        source, _, record = store.pop_out(ref)   # (ref is a quote of it now, where it was)
    pid, undo = store.new_paraphrase(source, record)
    def swap(data, blocks):   # the paraphrase where the quote was
        for holder in store.parents(blocks, ref):
            undo["blocks"].setdefault(holder, store.copy.deepcopy(blocks[holder]))
            store.with_children(blocks[holder], [pid if k == ref else k for k in store.children(blocks[holder])])
        undo["blocks"].setdefault(ref, store.copy.deepcopy(blocks[ref]))
    store.transact(swap)
    return pid, undo


def links_json(library: dict, b: dict) -> list:
    """A block of text's hyperlinks, as the page marks them: where, to what (and its title)."""
    return [{"to": l["to"], "at": l["at"], "title": library[l["to"]]["title"] if l["to"] in library else "gone"}
            for l in store.links(b)]


def masking_json(library: dict, qid: str) -> dict:
    """What masking quote `qid` works on (the terminal's masking mode): its target's whole draft, the mask as
    it's edited (fw_lens.edit_mask: all of it when unmasked), and the draft's lines as the page draws them,
    each with where it starts in the draft (marker lines left out: a block's lines carry its id)."""
    blocks = blocks_of(library)
    target, mask = store.quoted(blocks[qid])
    draft = store.block_draft(blocks, target)
    lines, pos, block = [], 0, None
    for line in draft.split("\n"):
        m = store.BLOCK_RE.fullmatch(line)
        if m:
            block = m.group(1)
        elif (q := store.QUOTE_RE.fullmatch(line)):
            lines.append({"t": "quote", "start": pos, "end": pos + len(line),
                          "title": library[q.group(1)]["title"] if q.group(1) in library else "missing block",
                          "data": kept_json(library, line, 2, (target,))})
        elif store.IMAGE_RE.fullmatch(line):
            lines.append({"t": "picture", "start": pos, "end": pos + len(line), "data": kept_json(library, line, 2, (target,))})
        else:
            lines.append({"t": "text", "start": pos, "text": line, "block": block})
        pos += len(line) + 1
    return {"quote": qid, "target": target, "title": library[target]["title"], "draft": draft,
            "mask": store.edit_mask(draft, mask), "lines": lines}


def mask_op(draft: str, mask: list, op: str, a: int = 0, b: int = 0, i: int = 0) -> list:
    """One key while masking, on the mask being edited (fw_lens's interval set), kept well formed:
    `[` on a selection a..b shows exactly it (wrap), `]` hides it (minus); `[` at a point a opens there
    (open_at), `]` closes (close_at); Backspace on bracket i takes it out (drop_anchor)."""
    n = len(draft)
    got = {"wrap": lambda: store.wrap(mask, a, b), "minus": lambda: store.minus(mask, a, b),
           "open": lambda: store.open_at(mask, a, n), "close": lambda: store.close_at(mask, a, n),
           "drop": lambda: store.drop_anchor(mask, i, n)}[op]()
    return store.tidy_edit(draft, got)


def clip_unit(blocks: dict, ref: str) -> dict:
    """Block `ref` as the rich clipboard keeps it (the terminal's units, fw_blocks: so either editor can paste
    it): a quote's content, a picture's file, a container's blocks, a block of text's text and links."""
    b = blocks[ref]
    if store.quoted(b):
        return {"id": ref, "quote": store.copy.deepcopy(b["content"]), "shown": store.shown_text(blocks, ref)}
    if store.image_of(b):
        return {"id": ref, "image": store.image_of(b)}
    if store.children(b):
        return {"id": ref, "blocks": [clip_unit(blocks, k) for k in store.children(b) if k in blocks]}
    return {"id": ref, "text": store.own_text(blocks, ref), "links": store.links(b)}


def maybes_json(library: dict, kid: str) -> list:
    """A kind's maybes (fw_block.maybes: the pericopes a model guesses might be one, likeliest first), each where it
    lives, to review from the kind."""
    blocks = blocks_of(library)
    return [{"block": b, "home": store.home_of(blocks, b)[0], "title": library[b]["title"], "p": round(p, 2)}
            for b, p in store.maybes(store.load_guesses(), library, kid) if b in library]


def kind_tokens(library: dict, ref: str) -> list:
    """The header's kinds line, as the terminal's (Editor.kind_chips): each answer (`yes`: true, false), then a
    model's guesses that count (store.guessed): a learned kind's applied ("applied"), any other a guess
    ("guess", its p)."""
    b = library[ref]["block"]
    out = [{"kind": k, "name": library[k]["title"], "mark": "yes" if yes else "no"}
           for k, yes in store.kinds_of(b).items() if store.kind_of(library.get(k, {}).get("block")) is not None]
    data = store.load_guesses()
    auto = store.learned(data)
    for k, p in store.guessed(data, library).get(ref, {}).items():
        out.append({"kind": k, "name": library[k]["title"], "p": round(p, 2),
                    "mark": "applied" if store.is_applied(library, ref, k, auto) else "guess"})
    return out


def pericope_json(library: dict, ref: str) -> dict:
    """A pericope (or any block) as the page opens it: its header and what it holds."""
    blocks = blocks_of(library)
    b = blocks[ref]
    found = store.backlinks(blocks, ref)
    return {"id": ref, "title": b.get("title"), "shown": library[ref]["title"],
            "type": store.type_label(b), "kind": store.kind_of(b) is not None,
            "created": b.get("created"), "updated": b.get("updated"), "words": b.get("words", 0),
            "kinds": store.kinds_text(blocks, b), "kindTokens": kind_tokens(library, ref),
            "maybes": maybes_json(library, ref) if store.kind_of(b) is not None else None,
            "backlinks": store.backlink_summary(found) if found else "",
            "base": store.content_hash(blocks, ref), "children": tree_json(library, ref, 1, (ref,))}


def preview(blocks: dict, ref: str, chars: int = 240, pictures: int = 2) -> list:
    """What a card shows of `ref`, in order: its text and pictures as they come, through quotes too (each block
    once, masks kept, as full_text), until about `chars` of text or `pictures` pictures. [{t: text, text} |
    {t: image, file}], neighbouring text run together."""
    if ref not in blocks:
        return []
    own = store.image_of(blocks[ref])
    if own:
        return [{"t": "image", "file": own}]
    out, seen, left = [], {ref}, {"chars": chars, "pictures": pictures}

    def add_text(text):
        text = " ".join(shown_text(text).split())
        if not text or left["chars"] <= 0:
            return
        text = text[:left["chars"]]
        left["chars"] -= len(text)
        if out and out[-1]["t"] == "text":
            out[-1]["text"] += " " + text
        else:
            out.append({"t": "text", "text": text})

    def walk(items):
        for item in items:
            if left["chars"] <= 0 and left["pictures"] <= 0:
                return
            match item:
                case ("text", text):
                    add_text(text)
                case ("image", i) if left["pictures"] > 0:
                    f = store.image_of(blocks.get(i))
                    if f:
                        left["pictures"] -= 1
                        out.append({"t": "image", "file": f})
                case ("quote", target, mask, _, inner) if target in blocks and target not in seen:
                    seen.add(target)
                    if store.image_of(blocks[target]):
                        walk([("image", target)])
                    else:
                        walk(store.quote_items(blocks, target, mask, inner=inner))
    walk(store.block_items(blocks, ref))
    return out


GARDEN = 12   # the garden's cards: the first this many (the user, 2026-11-18); the rest are found by searching


def home_json(library: dict) -> list:
    """The garden: the first GARDEN pericopes in its order, each with what a card says. Pictures are left out
    (the user, 2026-11-18: searching finds them)."""
    blocks = blocks_of(library)
    refs = sorted((r for r, e in library.items() if e["entry"] and not store.image_of(blocks[r])), reverse=True)
    now = int(store.clock() // 60)
    out = []
    for i, _ in store.garden(blocks, refs, now)[:GARDEN]:
        what, when = store.last_action(blocks[i])
        out.append({"key": i, "title": library[i]["title"], "right": f"{i[4:6]}/{i[6:8]}  {library[i].get('words', 0)}w",
                    "last": f"{what} {store.ago(when, now)}".strip(), "kind": store.kind_of(blocks[i]) is not None,
                    "preview": preview(blocks, i)})
    return out


def library_json(library: dict) -> list:
    """The whole library, below the garden (the user, 2026-11-18): every pericope, newest first, a line each."""
    return [{"key": i, "title": library[i]["title"], "right": f"{i[4:6]}/{i[6:8]}  {library[i].get('words', 0)}w",
             "kind": store.kind_of(library[i]["block"]) is not None}
            for i in sorted((r for r, e in library.items() if e["entry"]), reverse=True)]


def search_json(library: dict, query: str, meaning: list | None = None) -> list:
    """Home's search, as the terminal's: fw_picker.Picker's rows (with the
    mini's answer, `meaning`, mixed in when there is one)."""
    refs = sorted((r for r, e in library.items() if e["entry"]), reverse=True)
    p = Picker(library, refs, pinned=[(NEW, lambda q: f"+ new pericope “{q}”" if q else "+ new pericope")],
               inside=blocks_inside(library, refs))
    p.query = query
    if meaning is not None:
        p.meaning = (query, meaning)
    blocks = blocks_of(library)
    rows = []
    for key, shown, right, *dim in p.rows():
        home = key if key == NEW or library[key]["entry"] else store.home_of(blocks, key)[0]
        rows.append({"key": "new" if key == NEW else key, "label": shown, "right": right, "dim": bool(dim and dim[0]),
                     "open": home, "at": None if key in (NEW, home) else p.source(key),
                     "source": None if key == NEW else p.source(key),          # what quoting this row quotes
                     "inside": key != NEW and key != home and not store.quoted(blocks.get(key))})  # a block inside a pericope
    return rows


# --- the server ----------------------------------------------------------------

def library() -> dict:
    return store.build_library(store.load_data())


def stamp() -> int:
    try:
        return store.DATA_PATH.stat().st_mtime_ns
    except OSError:
        return 0


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        ask = parse_qs(url.query)
        path = url.path
        try:
            if path == "/" or path == "/index.html":
                return self.file(WEB / "index.html")
            if path.startswith("/dist/"):
                return self.file(WEB / "dist" / Path(path[len("/dist/"):]).name)
            if path.startswith("/images/"):
                name = path[len("/images/"):]
                return self.file(store.IMAGES_PATH / name) if IMAGE_RE.match(name) else self.send(404, {"error": "no such picture"})
            if path == "/api/stamp":
                return self.send(200, {"stamp": stamp()})
            if path == "/api/keys":   # the user's key bindings (#/keys), over the page's defaults
                return self.send(200, {"keys": read_keys()})
            if path == "/api/version":   # the code this core started with, and the page built now (the page reloads on a change)
                return self.send(200, {"code": CODE, "page": page_stamp(), "store": str(store.DATA_PATH)})
            if path == "/api/home":
                lib = library()
                return self.send(200, {"count": sum(1 for e in lib.values() if e["entry"]), "rows": home_json(lib), "library": library_json(lib)})
            if path == "/api/search":
                q = (ask.get("q") or [""])[0]
                meaning = None
                if (ask.get("meaning") or ["0"])[0] == "1" and fw_meaning.URL not in ("", "off") \
                        and len(q.strip()) >= fw_meaning.MIN_CHARS:
                    try:
                        meaning = fw_meaning.fetch(fw_meaning.URL, q)
                    except (OSError, ValueError):
                        meaning = None
                return self.send(200, {"query": q, "rows": search_json(library(), q, meaning), "meaning": meaning is not None})
            if path == "/api/masking":   # what masking a quote works on (masking_json)
                qid = (ask.get("quote") or [""])[0]
                lib = library()
                if not store.quoted((lib.get(qid) or {}).get("block")):
                    return self.send(404, {"error": "no such quote"})
                return self.send(200, masking_json(lib, qid))
            if path == "/api/clip":   # what fw last clipped (the rich clipboard, shared with the terminal), or {}
                return self.send(200, store.load_clip() or {})
            if path == "/api/blocks":   # ?ids=a,b: blocks as the page edits them, keeping their ids (a cut, pasted: moved)
                lib = library()
                ids = [i for i in (ask.get("ids") or [""])[0].split(",") if i in lib]
                return self.send(200, {"blocks": [node_json(lib, i) for i in ids]})
            if path == "/api/kinds":   # every kind: {id, name}, oldest first (the kinds picker)
                lib = library()
                return self.send(200, {"kinds": [{"id": k, "name": lib[k]["title"]} for k in store.kind_ids(lib)]})
            if path == "/api/quote":   # a new quote of `target`, as the page draws it (what it shows, what it holds)
                target = (ask.get("target") or [""])[0]
                lib = library()
                if target not in lib:
                    return self.send(404, {"error": "no such block"})
                # where it's going (`into`: the block it'll be in and what holds it; `depth`: quotes around it there).
                # Never refused (the user, 2026-11-19): the data model allows any quote, however deep what it quotes
                # goes, or if it comes back round to here; the drawing decides what to show (⋯ past the depth, ↻ at a
                # cycle). Its first drawing starts from here, so it stops where it would show itself even before it's saved
                into, depth = (ask.get("into") or [""])[0], int((ask.get("depth") or ["0"])[0] or 0)
                blocks = blocks_of(lib)
                here = tuple(i for i in into.split(",") if i in blocks)
                return self.send(200, quote_json(lib, None, target, None, [], {}, depth + 1, here))
            m = re.fullmatch(r"/api/pericope/([^/]+)", path)
            if m and ID_RE.match(m.group(1)):
                lib = library()
                if m.group(1) not in lib:
                    return self.send(404, {"error": "no such pericope"})
                return self.send(200, pericope_json(lib, m.group(1)))
            return self.send(404, {"error": "not found"})
        except (store.StoreError, OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    def do_PUT(self):
        if urlparse(self.path).path == "/api/keys":   # {keys}: the user's key bindings, kept
            try:
                keys = self.body().get("keys") or {}
                write_keys({k: v for k, v in keys.items() if isinstance(k, str) and isinstance(v, str)})
                return self.send(200, {"keys": read_keys()})
            except (OSError, ValueError) as e:
                return self.send(500, {"error": str(e)})
        lens = re.fullmatch(r"/api/lens/([^/]+)", urlparse(self.path).path)
        if lens and ID_RE.match(lens.group(1)):   # {text, base}: a masked quote's view, written through (store.commit_view)
            try:
                body = self.body()
                hashes, _ = store.commit_view(lens.group(1), body.get("text") or "", None, base=body.get("base"))
                return self.send(200, {"bases": hashes})
            except store.StoreError as e:
                return self.send(409, {"error": str(e)})
            except (OSError, ValueError) as e:
                return self.send(500, {"error": str(e)})
        m = re.fullmatch(r"/api/pericope/([^/]+)", urlparse(self.path).path)
        if not (m and ID_RE.match(m.group(1))):
            return self.send(404, {"error": "not found"})
        try:
            body = self.body()
            fields = [{"key": "title", "value": body.get("title") or "", "editable": True}] if "title" in body else []
            notes, base, _, _ = store.commit(m.group(1), body.get("draft"), fields, final=bool(body.get("final")),
                                             base=body.get("base"))
            blocks = blocks_of(library())
            also = {i: store.content_hash(blocks, i) for i in body.get("also") or [] if i in blocks}
            return self.send(200, {"base": base, "notes": notes, "gone": m.group(1) not in blocks, "bases": also})
        except store.StoreError as e:
            return self.send(409, {"error": str(e)})
        except (OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/pericope":   # a new pericope ({title})
                title = (self.body().get("title") or "").strip() or None
                def make(data, blocks):
                    return store.add_block(data, blocks, store.new_id(blocks), [], title=title, entry=True)["id"]
                ref = store.transact(make, tidy=False)   # (its base too: home's waiting pericope saves into it at once)
                return self.send(200, {"id": ref, "base": store.content_hash(blocks_of(library()), ref)})
            if path == "/api/popout":   # {block}: a pericope of its own, quoted where it was (store.pop_out)
                ref = self.body().get("block")
                entry, _, _ = store.pop_out(ref)
                return self.send(200, {"id": entry})
            if path == "/api/act":   # the Ctrl+/ menu's actions, each a store function; its undo record comes back
                body = self.body()
                do, q = body.get("do"), body.get("quote")
                if do == "detach":            # Turn into text
                    _, _, record = store.detach(q)
                    return self.send(200, {"record": record})
                if do == "popout":            # Turn into a quote (and open it)
                    entry, _, record = store.pop_out(body.get("block"))
                    return self.send(200, {"id": entry, "record": record})
                if do == "setmask":           # masking done: the mask, anchors into `draft` (moved onto the stored text)
                    _, record = store.set_quote_mask(q, body.get("draft"), body.get("mask"))
                    return self.send(200, {"record": record})
                if do == "showall":           # Remove mask
                    _, record = store.set_quote_mask(q, None, None, inner=True)
                    return self.send(200, {"record": record})
                if do == "show":              # its top line: what it shows of its source
                    _, record = store.set_quote_show(q, list(body.get("show") or []))
                    return self.send(200, {"record": record})
                if do == "lock":              # Lock / Unlock writing through
                    _, record = store.set_quote_lock(q, bool(body.get("on")))
                    return self.send(200, {"record": record})
                if do == "link":              # Link to a pericope: a span of a block of text (to a new one, titled)
                    to, record = store.link_text(body.get("block"), body.get("text") or "", body.get("at"),
                                                 body.get("to"), body.get("title"))
                    return self.send(200, {"to": to, "title": library()[to]["title"], "record": record})
                if do == "unlink":            # Remove link (the text stays)
                    record = store.unlink_text(body.get("block"), body.get("to"), body.get("at"))
                    return self.send(200, {"record": record})
                if do == "kind":              # an answer: block is (true) or isn't (false) a kind, or none (null); a new kind by `name`
                    kid, record = store.set_kind(body.get("block"), body.get("kind"), body.get("answer"), body.get("name") or "")
                    return self.send(200, {"kind": kid, "record": record})
                if do == "rename":            # a kind's name (its title): refused empty, or another kind's
                    record = store.rename_kind(body.get("kind"), body.get("name") or "")
                    return self.send(200, {"record": record})
                if do == "paraphrase_it":     # Paraphrase it: your words in its place (paraphrase_it)
                    pid, record = paraphrase_it(body.get("block"))
                    return self.send(200, {"id": pid, "record": record})
                if do == "paraphrase":        # Paraphrases… (`source`) / Not a paraphrase (no source)
                    record = store.set_paraphrase(body.get("block"), body.get("source"))
                    return self.send(200, {"record": record})
                if do == "delete":            # Delete this pericope (quotes of it elsewhere keep its last text)
                    return self.send(200, {"quotes": store.delete_entry(body.get("pericope"))})
                return self.send(404, {"error": f"no action {do!r}"})
            if path == "/api/clip":   # {ids, cut, text}: blocks clipped (save_clip: a cut one kept while it's held)
                body = self.body()
                blocks = blocks_of(library())
                ids = [i for i in body.get("ids") or [] if i in blocks]
                store.save_clip({"text": body.get("text") or "", "blocks": [clip_unit(blocks, i) for i in ids],
                                 **({"cut": True} if body.get("cut") else {})} if ids else None)
                return self.send(200, {"ok": True})
            if path == "/api/maskop":   # {draft, mask, op, a, b, i}: one key while masking (mask_op), the mask back
                body = self.body()
                return self.send(200, {"mask": mask_op(body["draft"], body["mask"], body["op"], int(body.get("a") or 0),
                                                       int(body.get("b") or 0), int(body.get("i") or 0))})
            if path == "/api/restore":   # {record}: an action taken back (store.restore); its inverse comes back
                return self.send(200, {"record": store.restore(self.body().get("record") or {"blocks": {}})})
            if path == "/api/maskto":   # {quote, block}: the quote masked to just that block (store.mask_quote_to)
                body = self.body()
                store.mask_quote_to(body.get("quote"), body.get("block"))
                lib = library()
                b = blocks_of(lib)
                return self.send(200, node_json(lib, body.get("quote")) if body.get("quote") in b else {})
            if path == "/api/picture":   # a picture pericope: {url} downloaded, or the picture's own bytes (dropped)
                if (self.headers.get("Content-Type") or "").startswith("image/"):
                    n = int(self.headers.get("Content-Length") or 0)
                    name = store.add_image_data(self.rfile.read(n), self.headers.get("X-Name") or "a dropped picture")
                else:
                    url = (self.body().get("url") or "").strip()
                    name = store.add_image_data(store.fetch_image(url), url)
                def make(data, blocks):
                    return store.add_block(data, blocks, store.new_id(blocks), {"image": name}, entry=True)["id"]
                ref = store.transact(make, tidy=False)   # (its base too: home's waiting pericope saves into it at once)
                return self.send(200, {"id": ref, "base": store.content_hash(blocks_of(library()), ref)})
            return self.send(404, {"error": "not found"})
        except store.StoreError as e:
            return self.send(409, {"error": str(e)})
        except (OSError, ValueError) as e:
            return self.send(500, {"error": str(e)})

    # --- plumbing
    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        got = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        if not isinstance(got, dict):
            raise ValueError("expected a JSON object")
        return got

    def send(self, code: int, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def file(self, path: Path):
        try:
            data = path.read_bytes()
        except OSError:
            return self.send(404, {"error": "not found"})
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if path.suffix in (".html", ".js", ".css") else "max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # (quiet)
        pass

    def handle(self):
        ACTIVE[0] += 1
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):   # (the page went away mid-answer: nothing to tell it)
            pass
        finally:
            ACTIVE[0] -= 1


def serve(port: int = PORT) -> ThreadingHTTPServer:
    """The server on 127.0.0.1:`port` (0: any free one), running in a thread."""
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main() -> int:
    ap = argparse.ArgumentParser(description="fw's web editor: a local server over the store")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FW_WEB_PORT", PORT)))
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--code-stamp", action="store_true", help="print which code this is, and stop (fw web compares)")
    a = ap.parse_args()
    if a.code_stamp:
        print(CODE)
        return 0
    store.cmd_migrate(None)  # (as fw does on every run: the store checked and brought up to date)
    if os.environ.get("FW_WEB_WATCH", "1") != "0":
        if page_stale():
            build_page()
        threading.Thread(target=keep_current, daemon=True).start()
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"fw web: {url}", file=sys.stderr, flush=True)
    if not a.no_open:
        webbrowser.open(url)
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
