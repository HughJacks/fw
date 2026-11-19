import json, os, sys
sys.path.insert(0, ".")
import drive
def click(x, y, b=0):  # xterm X10 encoding, 0-based x/y; press then release
    return "\x1b[M" + chr(32 + b) + chr(33 + x) + chr(33 + y) + "\x1b[M" + chr(35) + chr(33 + x) + chr(33 + y)
def wheel(up, x=5, y=2):
    return "\x1b[M" + chr(32 + (64 if up else 65)) + chr(33 + x) + chr(33 + y)
META = os.path.abspath("t/f.meta.json")
def meta(title=""):
    json.dump({"id": "X", "fields": [
        {"key": "id", "value": "20261021T000000-abcd", "editable": False},
        {"key": "title", "value": title, "editable": True}]}, open(META, "w"))
long = "aaaa bbbb cccc dddd eeee ffff gggg"   # wraps at width 17 (cols 28, past room for 3 boxes)
# the text sits in a box: its top on row 0, text from row 1, column 6
cases = [
  # (label, body, keys, args, want_body, want_title)
  ("click mid-line 2",              "hello world\nsecond line", [click(6 + 3, 2), "X", "\x11"], [], "hello world\nsecXond line", None),
  ("click past end of line",        "hi\nthere", [click(20, 0), "!", "\x11"], [], "hi!\nthere", None),
  ("click below the last line",     "hi\nthere", [click(5, 8), "!", "\x11"], [], "hi\nthere!", None),
  ("click on wrapped 2nd row",      long, [click(6 + 7, 2), "X", "\x11"], [], "aaaa bbbb cccc dddd eeXee ffff gggg", None),
  ("click in gutter = line start",  "hello", [click(0, 0), "X", "\x11"], [], "Xhello", None),
  ("click clears a selection",      "hello", ["\x01", click(6 + 1, 1), "X", "\x11"], [], "hXello", None),
  ("wheel down x2 moves 6 rows",      "\n".join(f"l{i}" for i in range(30)), [wheel(False), wheel(False), "X", "\x11"], [], None, None),
  ("click header title, type",      "body", [click(19, 2), "Z", "\x11"], ["--meta", META], "body", "abZcd"),
  ("header then click back to body","body", [click(19, 2), "Z", click(6 + 2, 5), "Y", "\x11"], ["--meta", META], "boYdy", "abZcd"),
]
ok = True
for label, body, keys, args, want_body, want_title in cases:
    meta("abcd")
    got = drive.run(body, keys, args, cols=28, rows=10)
    if want_body is None:
        line = [l for l in got.split("\n") if "X" in l]
        good = line == ["Xl6"]; print(f"{'ok' if good else 'FAIL':5} {label}: X landed on {line}"); ok &= good; continue
    title = json.load(open(META))["fields"][1]["value"] if args else None
    good = got == want_body and (want_title is None or title == want_title); ok &= good
    print(f"{'ok' if good else 'FAIL':5} {label}: {got!r}" + (f" title={title!r}" if args else "") + ("" if good else f"  want {want_body!r} {want_title!r}"))
print("MOUSE OK" if ok else "MOUSE FAILURES")
