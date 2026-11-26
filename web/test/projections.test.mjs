// projections.test.mjs — x.f: the receiver before a dot, a function's first argument, what's projectable first.
import { test } from "node:test";
import assert from "node:assert/strict";
import { receiverBefore, firstArg, projectionsFor, typeOf, projectable } from "../src/projections.js";

test("the receiver before a dot: a postfix chain", () => {
  const at = (t) => receiverBefore(t, t.length);
  assert.equal(at("1 + @20261001T100000-a000"), "@20261001T100000-a000");
  assert.equal(at("let n = this.title"), "this.title");
  assert.equal(at("f(@20261001T100000-a000).created"), "f(@20261001T100000-a000).created");
  assert.equal(at("[1, 2, (3)]"), "[1, 2, (3)]");
  assert.equal(at('x ++ "a.b"'), '"a.b"');
  assert.equal(at("wordCount("), "");
  assert.equal(projectable("21"), false);
  assert.equal(projectable("this"), true);
});

test("a function's first argument, from its signature", () => {
  assert.equal(firstArg("wordCount", "Ref -> Int"), "Ref");
  assert.equal(firstArg("before", "(Date, Date) -> Bool"), "Date");
  assert.equal(firstArg("writtenTitle", "Ref -> Option(String)"), "Ref");
  assert.equal(firstArg("length", ""), "[a]");
  assert.equal(firstArg("now", "Date"), null);
});

test("what fits first, then the rest; constants never", () => {
  const B = [["title", "Ref -> String", ""], ["year", "Date -> Int", ""], ["now", "Date", ""], ["length", "", ""]];
  assert.deepEqual(projectionsFor(B, "Date").map((p) => [p.label, p.fits]), [["year", true], ["title", false], ["length", false]]);
  assert.deepEqual(projectionsFor(B, "[Ref]").map((p) => p.label)[0], "length");
  assert.equal(typeOf(() => ({ kind: "value", type: "Ref" }), "this"), "Ref");
  assert.equal(typeOf(() => null, "this"), null);
});
