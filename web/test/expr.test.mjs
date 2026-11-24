// expr.test.mjs — the expression language, v1 (web/src/expr.js): parse, check, evaluate, holes.
import { test } from "node:test";
import assert from "node:assert/strict";
import { run, tokens, parse, check } from "../src/expr.js";

const value = (src) => { const r = run(src); assert.ok(r.done, `${src} -> ${r.text}`); return [r.text, r.type]; };

test("literals of each type, cast to text", () => {
  assert.deepEqual(value("42"), ["42", "Int"]);
  assert.deepEqual(value("2.5"), ["2.5", "Float"]);
  assert.deepEqual(value("10.0"), ["10.0", "Float"]);
  assert.deepEqual(value('"hi there"'), ["hi there", "String"]);
  assert.deepEqual(value("true"), ["true", "Bool"]);
  assert.deepEqual(value('"a\\"b\\nc"'), ['a"b\nc', "String"]);
});

test("arithmetic: precedence, Int stays whole, Float divides", () => {
  assert.deepEqual(value("1 + 2 * 3"), ["7", "Int"]);
  assert.deepEqual(value("(1 + 2) * 3"), ["9", "Int"]);
  assert.deepEqual(value("7 / 2"), ["3", "Int"]);
  assert.deepEqual(value("7.0 / 2.0"), ["3.5", "Float"]);
  assert.deepEqual(value("-3 - -4"), ["1", "Int"]);
  assert.deepEqual(value("10 - 2 - 3"), ["5", "Int"]);
});

test("strings, comparisons, booleans, if", () => {
  assert.deepEqual(value('"big" ++ "!"'), ["big!", "String"]);
  assert.deepEqual(value('if 3 * 4 > 10 then "big" ++ "!" else "small"'), ["big!", "String"]);
  assert.deepEqual(value("2.5 * 4.0 == 10.0 && not false"), ["true", "Bool"]);
  assert.deepEqual(value('"apple" < "banana"'), ["true", "Bool"]);
  assert.deepEqual(value("1 != 1 || 2 >= 2"), ["true", "Bool"]);
});

test("a type error is a hole; the rest still evaluates around it", () => {
  const r = run('1 + "a"');
  assert.equal(r.done, false);
  assert.match(r.text, /⦃\+ needs two of one type: Int and String⦄/);
  const s = run('(2 * 3) ++ "x"');
  assert.match(s.text, /⦃\+\+ needs two of one type: Int and String⦄/);
  assert.match(run("1 + 2.0").text, /Int and Float/);
  assert.match(run("if 1 then 2 else 3").text, /if needs a Bool, got Int/);
  assert.match(run('if true then 1 else "x"').text, /then and else must be one type/);
});

test("an unfinished expression: holes, worked out as far as it goes", () => {
  assert.equal(run("1 + 2 +").text, "3 + ⦃an expression to come⦄");
  assert.equal(run("2 * (3 + 4").text, "2 * (7 ⦃a ) to close it⦄");
  assert.match(run("if true then 5").text, /^5$/);   // (the branch taken has no hole: the else doesn't matter)
  assert.match(run("if false then 5").text, /⦃else …⦄/);
  assert.equal(run("false && (true ||)").text, "false");   // (short-circuit, around a hole)
  assert.match(run("x + 1").text, /nothing is called x/);
  assert.match(run("1 2").text, /nothing goes after it: 2/);
  assert.match(run("1 < 2 < 3").text, /one comparison at a time/);
  assert.match(run("4 / 0").text, /can't divide by zero/);
  assert.match(run('"open').text, /a string not closed/);
  assert.equal(run("   ").empty, true);
});

test("the pieces: tokens and a typed term", () => {
  assert.deepEqual(tokens("1 ++ x").map((t) => t.k), ["num", "sym", "name"]);
  assert.equal(check(parse("1 < 2")).ty, "Bool");
  assert.equal(check(parse("1 +")).ty, "Int");   // (a hole's unknown: the sum is still an Int)
});
