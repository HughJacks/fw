import json, os, sys
sys.path.insert(0, ".")
import drive, fwtest as F
from fwtest import check
S = F.use_store("t/store.json")
SELF, A = "20261021T230000-0000", "20261001T100000-aaaa"
C1, C2, CA = "20261021T230000-c001", "20261021T230000-c002", "20261001T100000-ca00"
META = os.path.abspath("t/f.meta.json")
Q = S.quote_line
UP, DOWN, LEFT, RIGHT, ESC, BS, DEL, HOME, END = "\x1b[A", "\x1b[B", "\x1b[D", "\x1b[C", "\x1b", "\x7f", "\x1b[3~", "\x1b[H", "\x1b[F"
ENTER, QUIT, UNDO, SDOWN = "\r", "\x11", "\x1a", "\x1b[1;2B"
AE = ENTER  # the new-block key
SHIFT_ENTERS = (("Shift+Enter (kitty protocol)", "\x1b[13;2u"), ("Shift+Enter (modifyOtherKeys)", "\x1b[27;2;13~"),
                ("Option+Enter", "\x1b\r"))  # (Ctrl+Enter makes a block inside: subblock_test)
def blk(i, content, title=None): return {"id": i, "title": title, "content": content, "words": 0, "created": "2026-10-21T23:00:00-04:00"}
def child(i): return {"ref": i}
def quote(i): return {"ref": i, "as": "quote"}
def fresh(*kids):
    """SELF holds `kids` [(id, text) or ("quote", ref)]; A holds "alpha body"."""
    blocks = [blk(A, [child(CA)], "Alpha"), blk(CA, "alpha body"), blk(SELF, [], "mine")]
    for k in kids:
        if k[0] == "quote": blocks[2]["content"].append(quote(k[1]))
        else: blocks[2]["content"].append(child(k[0])); blocks.append(blk(k[0], k[1]))
    json.dump({"schemaVersion": 4, "entries": [A, SELF], "blocks": blocks}, open("t/store.json", "w"))
    json.dump({"id": SELF, "fields": []}, open(META, "w"))
    return S.block_draft(S.index(S.load_data()), SELF)
def kids(i):
    B = S.index(S.load_data())
    return [(("quote", S.quoted(B[k])[0]) if S.quoted(B.get(k)) else (k, S.own_text(B, k))) for k in S.children(B[i])]
def texts(i): return [k[1] for k in kids(i)]
def ids(i): return [k[0] for k in kids(i)]
def run(draft, keys, **kw): return drive.run(draft, keys, ["--meta", META], cols=60, rows=20, **kw)

d = fresh((C1, "hello world")); run(d, [END, LEFT * 5, AE, QUIT])
check("Enter mid-line splits the block", texts(SELF) == ["hello ", "world"] and ids(SELF)[0] == C1 and ids(SELF)[1] != C1, kids(SELF))
d = fresh((C1, "hello world")); raw = run(d, [END, AE, "next", QUIT], raw=True)
check("Enter at the end: a new block to type in", texts(SELF) == ["hello world", "next"] and ids(SELF)[0] == C1, kids(SELF))
check("  the draft file names both blocks", raw == f"{S.block_line(C1)}\nhello world\n{S.block_line(ids(SELF)[1])}\nnext", repr(raw))
d = fresh((C1, "hello world")); run(d, [AE, UP, "top", QUIT])
check("Enter at a block's start: new block above, text keeps its id", texts(SELF) == ["top", "hello world"] and ids(SELF)[1] == C1, kids(SELF))
d = fresh((C1, "hello world")); run(d, [AE, QUIT])
check("  an empty new block isn't saved", kids(SELF) == [(C1, "hello world")], kids(SELF))
for label, key in SHIFT_ENTERS:
    d = fresh((C1, "hello world")); run(d, [END, key, "more", QUIT])
    check(f"{label} only breaks the line", kids(SELF) == [(C1, "hello world\nmore")], kids(SELF))
d = fresh((C1, "hello")); run(d, [END, "\x1b[200~", " pasted\rtwo lines", "\x1b[201~", ENTER, "after", QUIT])
check("a bracketed paste stays one block; Enter after it splits", texts(SELF) == ["hello pasted\ntwo lines", "after"], kids(SELF))
d = fresh((C1, "x"), ("quote", A)); run(d, [DOWN, DOWN, "in ", "\x1b[27u", ENTER, "out", "\x1b[113;5u"])
check("kitty-protocol Esc and Ctrl+Q work", texts(A) == ["in alpha body"] and texts(SELF)[-1] == "out", (kids(A), kids(SELF)))
d = fresh((C1, "hello world")); run(d, [END, LEFT * 5, AE, UNDO, QUIT])
check("undo joins the split back", kids(SELF) == [(C1, "hello world")], kids(SELF))
d = fresh((C1, "one"), (C2, "two")); run(d, [DOWN, HOME, BS, QUIT])
check("Backspace at a block's start merges it into the one above", kids(SELF) == [(C1, "onetwo")], kids(SELF))
check("  the merged block is erased from the store", C2 not in S.index(S.load_data()))
d = fresh((C1, "one"), (C2, "two")); run(d, [END, DEL, QUIT])
check("Delete at a block's end merges the next one", kids(SELF) == [(C1, "onetwo")] and C2 not in S.index(S.load_data()), kids(SELF))
d = fresh((C1, "one"), (C2, "two")); run(d, [END, LEFT, SDOWN, BS, QUIT])
check("a selection reaching the next block takes both whole; Backspace removes them", kids(SELF) == [], kids(SELF))
d = fresh((C1, "one two"), (C2, "three")); run(d, [DOWN, END, " four", QUIT])
check("an entry's words count all its blocks", S.index(S.load_data())[SELF]["words"] == 4, S.index(S.load_data())[SELF]["words"])
d = fresh((C1, "x"), ("quote", A)); run(d, [DOWN, AE, "new", QUIT])
check("Enter on a selected quote: new block below", texts(SELF)[:1] == ["x"] and kids(SELF)[1] == ("quote", A) and texts(SELF)[2] == "new", kids(SELF))
d = fresh((C1, "x"), ("quote", A)); run(d, [DOWN, DOWN, END, LEFT * 4, AE, QUIT])
check("Enter inside a quote splits the quoted entry's block", texts(A) == ["alpha ", "body"] and ids(A)[0] == CA and kids(SELF)[0] == (C1, "x"), kids(A))
d = fresh((C1, "a\n\nb")); run(d, [DOWN, "/", "\r", "\r", QUIT])
k = kids(SELF)
check("a quote put mid-block splits it", [x[1] for x in k] == ["a", A, "b"] and k[0][0] == C1 and k[2][0] not in (C1, "quote"), k)
d = fresh((C1, "hello")); run(d, [END, AE, "child text", 1.5, AE, "/", "\r", "\r", QUIT])
check("the / menu lists entries, not their blocks", kids(SELF)[-1] == ("quote", A), kids(SELF))
check("plain file: Enter is just a new line", drive.run("ab", [END, ENTER, "c", QUIT]) == "ab\nc")

# leaf -> list, straight through the store
json.dump({"schemaVersion": 4, "entries": [SELF], "blocks": [blk(SELF, "just text")]}, open("t/store.json", "w"))
S.commit(SELF, "changed text", [])
check("a block of plain text stays plain while it's one run", S.index(S.load_data())[SELF]["content"] == "changed text")
S.commit(SELF, "one\n{{block}}\ntwo", [])
B = S.index(S.load_data())
check("  and becomes a list of children once it has two", [S.own_text(B, k) for k in B[SELF]["content"]] == ["one", "two"], B[SELF]["content"])

# gutter: one number per block
fresh((C1, "one\nstill one"), (C2, "two"), ("quote", A))
open("t/g.txt", "w").write(S.block_draft(S.index(S.load_data()), SELF))
g = F.editor("t/g.txt", "--meta", META, cols=40, rows=10)
rows = [l.rstrip() for l in g.scr.display[:8]]
g.close()
check("gutter numbers blocks, each on its box's top: 1 (two lines), 2, 3 (quote)", [r[:1] for r in rows] == ["1", " ", " ", " ", "2", " ", " ", "3"] and "{{block" not in "".join(rows), rows)
# words: an inline expression ($…$, TYPE.md "Inline") counts as one word, never its code's tokens
check("words: an inline expression counts one, its code none", S.word_count("the train $wordCount(@20261001T100000-aaaa) + 1$ arrives") == 4)
check("  a lone $, or \\$, is just part of its word", S.word_count("a lone 300$ stays, 30\\$ each") == 6)
json.dump({"schemaVersion": 4, "entries": [SELF], "blocks": [blk(SELF, "see $1 + 2 + 3$ go")]}, open("t/store.json", "w"))
S.cmd_migrate(None)
check("  the stored count: three", S.index(S.load_data())[SELF]["words"] == 3, S.index(S.load_data())[SELF].get("words"))
# a word: something besides punctuation (fw_block.is_word; the page's isWord and Hazel's is_word, one rule)
check("words: a + or a ? alone isn't one (an unfinished value's `31 + ?` is one word)", S.word_count("31 + ?") == 1)
check("  nor a dash, a bullet, dots or a typographic mark; letters, digits, accents are", S.word_count("- café — naïve ... “x” 1974 •") == 4)
F.report("BLOCK")
