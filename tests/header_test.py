import json, os, sys
sys.path.insert(0, ".")
import drive
META = os.path.abspath("t/f.meta.json")
def meta(name=""):
    json.dump({"id": "X", "fields": [
        {"key": "id", "value": "20261021T000000-abcd", "editable": False},
        {"key": "name", "value": name, "editable": True},
        {"key": "title", "value": "", "editable": False},
        {"key": "created", "value": "2026-10-21T00:00:00-04:00", "editable": False}]}, open(META, "w"))
def name(): return json.load(open(META))["fields"][1]["value"]
UP, DOWN = "\x1b[A", "\x1b[B"
cases = [
  ("Up enters header, type name, Down back to text", "abc", "", [UP, "journal", DOWN, "X", "\x11"], ("Xabc", "journal")),
  ("Esc leaves header",            "abc", "", [UP, "n", "\x1b", "Y", "\x11"], ("Yabc", "n")),
  ("Enter leaves header",          "abc", "", [UP, "n", "\r", "Z", "\x11"], ("Zabc", "n")),
  ("edit existing name",           "abc", "old", [UP, "\x7f\x7f\x7f", "new", "\x11"], ("abc", "new")),
  ("Up from 2nd line stays in text","a\nb", "", ["\x1b[B", UP, "Q", "\x11"], ("Qa\nb", "")),
  ("header edit alone autosaves",  "abc", "", [UP, "solo", 1.5], ("abc", "solo")),
]
ok = True
for label, body, n, keys, want in cases:
    meta(n)
    got_body = drive.run(body, keys, ["--meta", META], cols=50, sig=9 if label.endswith("autosaves") else None)
    got = (got_body, name())
    good = got == want; ok &= good
    print(f"{'ok' if good else 'FAIL':5} {label}: {got!r}" + ("" if good else f" want {want!r}"))
print("HEADER OK" if ok else "HEADER FAILURES")
