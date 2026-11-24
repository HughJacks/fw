// the page's pure part: run with `npm test` (node --test)
import { test } from "node:test";
import assert from "node:assert/strict";
import { newId, pmDoc, draftOf, freshIds, inline, pmLens, lensOf, deriveTitle } from "../src/draft.js";

const A = "20261001T100000-a000", B = "20261001T100000-b000", C = "20261001T100000-c000", Q = "20261001T100000-dddd";

test("a new id looks like fw's", () => {
  assert.match(newId(new Date(2026, 10, 17, 9, 5, 3), () => 0.5), /^20261117T090503-8000$/);
});

test("the core's tree -> the document -> fw's draft", () => {
  const doc = pmDoc([
    { t: "text", id: A, text: "one\ntwo" },
    { t: "container", id: C, children: [{ t: "text", id: B, text: "inside" }, { t: "quote", id: Q, target: A }] },
  ]);
  assert.equal(doc.content[0].content.length, 3);   // "one", a hard break, "two"
  assert.equal(draftOf(doc), `{{block ${A}}}\none\ntwo\n{{block ${B} ${C}}}\ninside\n{{quote ${A} ${Q} ${C}}}`);
});

test("nothing written: one empty block to write in", () => {
  assert.deepEqual(pmDoc([]).content, [{ type: "text_block", attrs: { id: null } }]);
});

test("ids: none missing, none twice", () => {
  let n = 0;
  const got = freshIds([{ type: "text_block", id: A }, { type: "text_block", id: A }, { type: "hard_break" },
                       { type: "quote", id: null }], () => `20261117T000000-000${n++}`);
  assert.deepEqual([...got.entries()], [[1, "20261117T000000-0000"], [3, "20261117T000000-0001"]]);
});

test("a block of text saved as itself: its text alone, no marker", () => {
  const doc = pmDoc([{ t: "text", id: A, own: true, text: "just\ntext" }]);
  assert.equal(draftOf(doc), "just\ntext");
});

test("a block's links: marks over their spans, across lines", () => {
  const got = inline("see the LINK\nhere", [{ to: B, at: [8, 12], title: "beta" }]);
  assert.deepEqual(got.map((n) => [n.type, n.text || "", n.marks ? n.marks[0].attrs.to : null]),
    [["text", "see the ", null], ["text", "LINK", B], ["hard_break", "", null], ["text", "here", null]]);
});

test("a masked quote's view: through the document and back, exactly, holes and all", () => {
  const H = "\ue000";
  const segs = [{ t: "text", id: A, marker: `{{block ${A}}}`, empty: false, text: `${H}quick brown${H}\nmore` },
                { t: "line", line: `{{quote ${B} ${Q}}}`, title: "beta" },
                { t: "text", id: C, marker: `{{block ${C}}}`, empty: true, text: "" }];
  const doc = pmLens(segs, H);
  assert.equal(doc.content[0].content.filter((n) => n.type === "hole").length, 2);
  assert.equal(lensOf(doc, H), `{{block ${A}}}\n${H}quick brown${H}\nmore\n{{quote ${B} ${Q}}}\n{{block ${C}}}`);
});

test("the derived title, as fw_block.derive_title", () => {
  assert.equal(deriveTitle("\n  # Hello there.\nmore"), "Hello there");
  assert.equal(deriveTitle("---\n“quoted”"), "quoted");
  assert.equal(deriveTitle("   \n"), null);
  const long = "word ".repeat(20);
  assert.equal(deriveTitle(long), "word ".repeat(12).trim() + "…");
});

test("snapNode: the editor's document as the expression engine reads it", async () => {
  const { snapNode } = await import("../src/draft.js");
  const doc = { type: "doc", content: [
    { type: "text_block", attrs: { id: "t1" }, content: [{ type: "text", text: "one" }, { type: "hard_break" },
      { type: "text", text: "two", marks: [{ type: "link", attrs: { to: "L" } }] }] },
    { type: "container", attrs: { id: "c1" }, content: [
      { type: "quote", attrs: { id: "q1", target: "P" } },
      { type: "text_block", attrs: { id: "p1", para: { id: "S", title: "s", text: "" } }, content: [{ type: "text", text: "said" }] }] },
    { type: "expr", attrs: { id: "e1", source: "1 + 2" } }] };
  assert.deepEqual(snapNode(doc), { id: "", t: "blocks", children: [
    { id: "t1", t: "text", text: "one\ntwo", links: [{ to: "L", at: [4, 7] }] },   // (its links: offsets, a line break one)
    { id: "c1", t: "blocks", children: [{ id: "q1", t: "quote", target: "P" }, { id: "p1", t: "paraphrase", target: "S", text: "said" }] },
    { id: "e1", t: "expr", source: "1 + 2" }] });
  const own = { type: "doc", content: [{ type: "text_block", attrs: { id: "X", own: true }, content: [{ type: "text", text: "just" }] }] };
  assert.deepEqual(snapNode(own), { id: "X", t: "text", text: "just", links: [] });
});
