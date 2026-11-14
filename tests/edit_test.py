import json, os, sys
sys.path.insert(0, ".")
import drive, fwtest as F
S = F.use_store("t/store.json")
SELF, A, B = "20261021T230000-0000", "20261001T100000-aaaa", "20261002T100000-bbbb"
Q = lambda ref: "{{quote " + ref + "}}"
META = os.path.abspath("t/f.meta.json")
def entry(i, title, blocks): return {"id": i, "title": title, "content": blocks, "words": 1, "created": "2026-10-01T10:00:00-04:00"}
def text(i): return S.own_text(S.index(S.load_data()), i)
def blocks(i):
    B = S.index(S.load_data())
    return [("quote", S.quoted(B[k])[0]) if S.quoted(B.get(k)) else ("child", k) for k in S.children(B[i])]
def v3(body):  # an old-style (v3) entry body: the store upgrades it on load
    out = []
    for part in __import__("re").split(r"(\{\{quote \S+\}\})", body):
        m = S.QUOTE_RE.fullmatch(part)
        if m: out.append({"type": "quote", "ref": m.group(1)})
        elif part.strip("\n"): out.append({"type": "text", "text": part.strip("\n")})
    return out
UP, DOWN, LEFT, RIGHT, ESC, BS, END = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\x1b", "\x7f", "\x1b[F"
def click(x, y): return "\x1b[M" + chr(32) + chr(33 + x) + chr(33 + y) + "\x1b[M" + chr(35) + chr(33 + x) + chr(33 + y)
cases = [
  # label, root draft, keys, want root draft, {entry: want text}
  ("Down into a quote, type: edits the source", f"x\n{Q(A)}\ny", [DOWN, DOWN, "NEW ", "\x11"], f"x\n{Q(A)}\ny", {A: "NEW alpha body"}),
  ("Up from below lands at the quote's end",     f"x\n{Q(A)}\ny", [DOWN, DOWN, DOWN, DOWN, UP, UP, END, "!", "\x11"], f"x\n{Q(A)}\ny", {A: "alpha body!"}),
  ("Right from end of line above enters",        f"x\n{Q(A)}\ny", [END, RIGHT, RIGHT, "R", "\x11"], f"x\n{Q(A)}\ny", {A: "Ralpha body"}),
  ("Left from line below enters at the end",     f"x\n{Q(A)}\ny", [DOWN, DOWN, DOWN, DOWN, LEFT, LEFT, "L", "\x11"], f"x\n{Q(A)}\ny", {A: "alpha bodyL"}),
  ("Right off the end of a quote comes out",     f"x\n{Q(A)}\ny", [DOWN, DOWN, END, RIGHT, RIGHT, "O", "\x11"], f"x\n{Q(A)}\nOy", {A: "alpha body"}),
  ("Enter inside a quote splits its text",       f"x\n{Q(A)}", [DOWN, DOWN, RIGHT * 5, "\r", "\x11"], f"x\n{Q(A)}", {A: "alpha\n body"}),
  ("Backspace inside a quote",                   f"x\n{Q(A)}", [DOWN, DOWN, END, BS * 5, "\x11"], f"x\n{Q(A)}", {A: "alpha"}),
  ("undo inside a quote",                        f"x\n{Q(A)}", [DOWN, DOWN, END, " more", "\x1a", "\x11"], f"x\n{Q(A)}", {A: "alpha body"}),
  ("click into the quote's text",                f"x\n{Q(A)}", [click(6 + 3, 4), "Q", "\x11"], f"x\n{Q(A)}", {A: "alpQha body"}),
  ("Esc then Backspace removes the quote only",  f"x\n{Q(A)}\ny", [DOWN, DOWN, ESC, BS, "\x11"], "x\ny", {A: "alpha body"}),
  ("nested: edit A inside B",                    f"x\n{Q(B)}", [DOWN, DOWN, DOWN, DOWN, "deep ", "\x11"], f"x\n{Q(B)}", {A: "deep alpha body", B: "beta"}),
  ("/ inside a quote adds a quote to the source", f"x\n{Q(B)}", [DOWN, DOWN, END, "\r", "/", "\r", "alpha", "\r", "\x11"], f"x\n{Q(B)}", {}),
  ("select-all inside a quote stays in it",      f"x\n{Q(A)}\ny", [DOWN, DOWN, "\x01", "z", "\x11"], f"x\n{Q(A)}\ny", {A: "z"}),
  ("Enter on a selected quote: new line below", f"{Q(A)}", ["\r", "n", "\x11"], f"{Q(A)}\nn", {A: "alpha body"}),
  ("Esc inside, then Enter: new line below",    f"x\n{Q(A)}", [DOWN, DOWN, ESC, "\r", "e", "\x11"], f"x\n{Q(A)}\ne", {A: "alpha body"}),
  ("Down past the entry's last quote: new line", f"x\n{Q(A)}", [DOWN, DOWN, DOWN, DOWN, "n", "\x11"], f"x\n{Q(A)}\nn", {A: "alpha body"}),
  ("Right past the entry's last quote: new line", f"x\n{Q(A)}", [DOWN, DOWN, END, RIGHT, RIGHT, "r", "\x11"], f"x\n{Q(A)}\nr", {A: "alpha body"}),
  ("nested at the end: out of A, out of B, new line", f"x\n{Q(B)}", [DOWN] * 4 + [DOWN, DOWN, DOWN, "n", "\x11"], f"x\n{Q(B)}\nn", {A: "alpha body"}),
  ("Up on a quote at the very top doesn't loop", f"{Q(A)}\ny", [DOWN, UP, UP, UP, UP, "\x1b[B", "\x1b[B", "\x1b[B", "\x1b[B", "k", "\x11"], f"{Q(A)}\nky", {A: "alpha body"}),
  ("Down: selected, inside, selected, past",     f"x\n{Q(A)}\ny", [DOWN, DOWN, DOWN, DOWN, "Z", "\x11"], f"x\n{Q(A)}\nZy", {A: "alpha body"}),
  ("Down then Up on a selected quote goes back", f"x\n{Q(A)}\ny", [DOWN, UP, "W", "\x11"], f"Wx\n{Q(A)}\ny", {A: "alpha body"}),
  ("Up out of a quote selects it; Up again past", f"x\n{Q(A)}\ny", [DOWN, DOWN, UP, UP, "U", "\x11"], f"Ux\n{Q(A)}\ny", {A: "alpha body"}),
  ("Right: selected, inside, selected, past",    f"x\n{Q(A)}\ny", [END, RIGHT, RIGHT, END, RIGHT, RIGHT, "V", "\x11"], f"x\n{Q(A)}\nVy", {A: "alpha body"}),
  ("Esc then Down moves on, not back in",        f"x\n{Q(A)}\ny", [DOWN, DOWN, ESC, DOWN, "E", "\x11"], f"x\n{Q(A)}\nEy", {A: "alpha body"}),
  ("quote at the top: Up from below goes in",    f"{Q(A)}\ny", [DOWN, UP, UP, END, "T", "\x11"], f"{Q(A)}\ny", {A: "alpha bodyT"}),
  ("leaving saves at once (killed right after)", f"x\n{Q(A)}\ny", [DOWN, DOWN, "now ", DOWN], f"x\n{Q(A)}\ny", {A: "now alpha body"}),
]
ok = True
for label, body, keys, want, want_store in cases:
    json.dump({"id": SELF, "fields": []}, open(META, "w"))
    json.dump({"schemaVersion": 3, "freewrites": [
        entry(A, "Alpha", [{"type": "text", "text": "alpha body"}]),
        entry(B, "Beta", [{"type": "text", "text": "beta"}, {"type": "quote", "ref": A}]),
        entry(SELF, "mine", v3(body))]}, open("t/store.json", "w"))
    killed = label.startswith("leaving saves")
    got = drive.run(body, keys, ["--meta", META], cols=60, rows=20, sig=9 if killed else None)
    got_store = {i: text(i) for i in want_store}
    good = (got == want or killed) and got_store == want_store
    if label.startswith("/ inside"):
        good = got == want and [k for k, _ in blocks(B)] == ["child", "quote", "quote"] and blocks(B)[2][1] == A
        got_store = {B: blocks(B)}
    ok &= good
    print(f"{'ok' if good else 'FAIL':5} {label}: root={got!r} store={got_store}" + ("" if good else f"  want root={want!r} store={want_store}"))
print("EDIT OK" if ok else "EDIT FAILURES")
