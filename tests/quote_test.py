import json, os, sys
sys.path.insert(0, ".")
import drive
SELF, A, B, G = "20261021T230000-0000", "20261001T100000-aaaa", "20261002T100000-bbbb", "20261003T100000-9999"
Q = lambda ref: "{{quote " + ref + "}}"
META = os.path.abspath("t/f.meta.json")
def meta(): json.dump({"id": SELF, "fields": [{"key": "id", "value": SELF, "editable": False},
                                  {"key": "words", "value": "0", "editable": False},
                                  {"key": "title", "value": "", "editable": True}]}, open(META, "w"))
def entry(i, title, blocks): return {"id": i, "title": title, "content": blocks, "words": 1, "created": "2026-10-01T10:00:00-04:00"}
STORE = {"schemaVersion": 3, "freewrites": [
    entry(A, "Alpha note", [{"type": "text", "text": "alpha body"}]),
    entry(B, "Beta note", [{"type": "text", "text": "beta"}, {"type": "quote", "ref": A}]),
    entry(G, "garden notes", [{"type": "text", "text": "tulips"}]),
    entry(SELF, "this entry", [])]}
os.environ["FW_DATA"] = os.path.abspath("t/store.json")
UP, DOWN, ESC, BS, ENTER = "\x1b[A", "\x1b[B", "\x1b", "\x7f", "\r"
cases = [
  ("/ Enter Enter quotes newest block",  "", ["/", ENTER, ENTER, "\x11"], f"{Q(G)}\n"),
  ("/ filter 'alp' picks Alpha",         "", ["/", ENTER, "alp", ENTER, "\x11"], f"{Q(A)}\n"),
  ("/ Down picks the 2nd newest",        "", ["/", ENTER, DOWN, ENTER, "\x11"], f"{Q(B)}\n"),
  ("command filter 'quo' then pick",     "", ["/", "quo", ENTER, ENTER, "\x11"], f"{Q(G)}\n"),
  ("Esc keeps '/xyz' as text",           "", ["/", "xyz", ESC, "\x11"], "/xyz"),
  ("Backspace on empty query closes",    "", ["/", BS, "k", "\x11"], "k"),
  ("Backspace in block stage goes back", "", ["/", ENTER, BS, ENTER, ENTER, "\x11"], f"{Q(G)}\n"),
  ("/ mid-line is just a slash",         "a", ["\x1b[F", "/b", "\x11"], "a/b"),
  ("quote then keep typing below",       "", ["/", ENTER, ENTER, "after", "\x11"], f"{Q(G)}\nafter"),
  ("quote between text lines",           "top\n\nend", [DOWN, "/", ENTER, ENTER, "\x11"], f"top\n{Q(G)}\nend"),
  ("undo removes the quote",             "", ["/", ENTER, ENTER, "\x1a", "\x11"], ""),
  ("Down x3 goes through a quote and out", f"x\n{Q(B)}\ny", [DOWN] * 7 + ["Z", "\x11"], f"x\n{Q(B)}\nZy"),
  ("Up into quote, Esc Esc selects it; type", f"x\n{Q(B)}\ny", [DOWN] * 7 + [UP, "N", "\x11"], f"x\n{Q(B)}\nN\ny"),
  ("Backspace after quote: select, delete", f"x\n{Q(A)}\ny", [DOWN] * 4 + [BS, BS, "\x11"], "x\ny"),
  ("Backspace on empty line after quote", f"x\n{Q(A)}\n", [DOWN] * 4 + [BS, "\x11"], f"x\n{Q(A)}"),
  ("Delete at end of line before quote",  f"x\n{Q(A)}\ny", ["\x1b[F", "\x1b[3~", "\x1b[3~", "\x11"], "x\ny"),
  ("Right/End on a quote don't get stuck", f"{Q(A)}\ny", ["\x1b[F", "\x1b[C", "R", "\x11"], f"{Q(A)}\nRy"),
  ("typing on a selected quote opens a line", f"{Q(A)}", ["e", "\x11"], f"{Q(A)}\ne"),
  ("Enter on a cycle stand-in opens a line", f"{Q(SELF)}", [ENTER, "e", "\x11"], f"{Q(SELF)}\ne"),
  ("a selection reaching a quote takes both whole", f"ab\n{Q(A)}", ["\x1b[1;2B", BS, "\x11"], ""),
  ("select-all + type replaces quotes too", f"ab\n{Q(A)}\ncd", ["\x01", "z", "\x11"], "z"),
]
ok = True
for label, body, keys, want in cases:
    json.dump(STORE, open("t/store.json", "w")); meta()
    got = drive.run(body, keys, ["--meta", META], cols=60, rows=24)
    good = got == want; ok &= good
    print(f"{'ok' if good else 'FAIL':5} {label}: {got!r}" + ("" if good else f"  want {want!r}"))
print("QUOTE OK" if ok else "QUOTE FAILURES")
