import os, sys, json, subprocess
sys.path.insert(0, "."); import fwtest as F
from fwtest import same as check
S = F.use_store("t/store.json"); DEV = F.DEV
A, T, QE = "20261001T100000-aaaa", "20261002T100000-bbbb", "20261003T100000-cccc"
C1, C2 = "20261001T100000-c001", "20261001T100000-c002"
q, b1, b2 = S.quote_line(A), S.block_line(C1), S.block_line(C2)
check("trailing blank lines trimmed", S.draft_items(f"{b1}\nabc\n\n"), [("text", C1, "abc")])
check("blank lines around a quote are spacing", S.draft_items(f"{b1}\na\n\n{q}\n\n"), [("text", C1, "a"), ("quote", A, None)])
check("leading blank lines and whitespace-only lines", S.draft_items(f"{b1}\n\n  \nabc\n \n"), [("text", C1, "abc")])
check("paragraph breaks inside a block kept", S.draft_items(f"{b1}\na\n\nb"), [("text", C1, "a\n\nb")])
check("all blank: nothing", S.draft_items(f"{b1}\n\n\n \n"), [])
check("two blocks stay two", S.draft_items(f"{b1}\none\n{b2}\ntwo"), [("text", C1, "one"), ("text", C2, "two")])
check("blank edges trimmed per block", S.draft_items(f"{b1}\none\n\n{b2}\n\ntwo\n"), [("text", C1, "one"), ("text", C2, "two")])
items = S.draft_items(f"x\n{q}\ny")
check("text without markers: new blocks with fresh ids", [(i[0], i[2] if i[0] == "text" else i[1]) for i in items], [("text", "x"), ("quote", A), ("text", "y")])
check("  ... and the two ids differ", items[0][1] != items[2][1], True)
lines, bids = S.parse_draft(f"{b1}\none\n{b1}\ntwo")
check("a repeated marker is a new block", (lines, bids[0] == C1, bids[1] != C1), (["one", "two"], True, True))
check("format_draft inverts parse_draft", S.format_draft(*S.parse_draft(f"{b1}\none\n{q}\n{b2}\ntwo")), f"{b1}\none\n{q}\n{b2}\ntwo")

def entry(i, title, blocks): return {"id": i, "title": title, "content": blocks, "words": 1, "created": "2026-10-01T10:00:00-04:00"}
json.dump({"schemaVersion": 3, "freewrites": [
    entry(A, "alpha", [{"type": "text", "text": "alpha"}]),
    entry(T, "texty", [{"type": "text", "text": "some text\n\n"}]),          # the old bug's leftovers
    entry(QE, "ends in quote", [{"type": "text", "text": "intro"}, {"type": "quote", "ref": A}])]}, open("t/store.json", "w"))
subprocess.run([sys.executable, f"{DEV}/fw_store.py", "migrate"], check=True, capture_output=True)
d = S.load_data(); B = S.index(d)
check("migrate cleans stored trailing blank lines", S.own_text(B, T), "some text")
check("migrate: every text block is a child, the quote a Quote block", ["quote" if S.quoted(B[k]) else "child" for k in B[QE]["content"]], ["child", "quote"])
for i, label in ((QE, "entry ending in a quote"), (T, "text entry")):
    before = S.load_data()
    _, tmp, line = S.stage(i, append=True)
    draft = open(tmp).read()
    lines = S.parse_draft(draft)[0]
    print(f"      reopened {label}: editor ends {lines[-2:]!r}, cursor on line {line} of {len(lines)}")
    check(f"  cursor on the last line: {label}", int(line), len(lines))
    S.finish(i, tmp)   # quit without typing
    os.remove(tmp); os.remove(tmp[:-4] + ".meta.json")
    check(f"reopen + quit leaves the store as it was: {label}", S.load_data(), before)
F.report("TRIM")
