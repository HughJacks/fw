// expr.js — the expression language, v1 (the user, 2026-11-23: "a very simple expression language with types and no
// functions yet. no references either. just as a block"; inspired by Hazel). Pure: no DOM, `npm test` runs it.
//
//   types   Int, Float, String, Bool
//   terms   42  2.5  "text"  true  false  (e)
//           -e  not e  e * e  e / e  e + e  e - e  e ++ e
//           e == e  e != e  e < e  e <= e  e > e  e >= e  e && e  e || e
//           if e then e else e
//
// Hazel's idea, kept: an unfinished or ill-typed program still means something. Anything that doesn't parse, or
// doesn't type, is a hole (with what's wrong); everything else is checked and evaluated around it, so a block always
// shows something: its value, or the expression as far as it could be worked out, its holes marked ⦃…⦄.
// A block shows text for now (every value cast to text, `show`); casting to other block types comes later.

// --- the syntax: tokens -----------------------------------------------------------------------------------------

const KEYWORDS = new Set(["if", "then", "else", "true", "false", "not"]);
const SYMBOLS = ["++", "==", "!=", "<=", ">=", "&&", "||", "+", "-", "*", "/", "<", ">", "(", ")"];

/** `src` -> tokens {k: kind, v: value, at: [start, end]}: num (int or float), str, kw, sym, name (not a keyword:
 * nothing's named yet, so a hole), bad (a character the language doesn't have, or a string left open). */
export function tokens(src) {
  const out = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) { i++; continue; }
    const start = i;
    if (/[0-9]/.test(c)) {
      while (i < src.length && /[0-9]/.test(src[i])) i++;
      let float = false;
      if (src[i] === "." && /[0-9]/.test(src[i + 1] || "")) { float = true; i++; while (i < src.length && /[0-9]/.test(src[i])) i++; }
      const text = src.slice(start, i);
      out.push({ k: "num", v: float ? { t: "Float", v: parseFloat(text) } : { t: "Int", v: parseInt(text, 10) }, at: [start, i] });
      continue;
    }
    if (c === '"') {
      let s = "", closed = false;
      i++;
      while (i < src.length) {
        if (src[i] === "\\" && i + 1 < src.length) { const e = src[i + 1]; s += e === "n" ? "\n" : e === "t" ? "\t" : e; i += 2; continue; }
        if (src[i] === '"') { closed = true; i++; break; }
        s += src[i++];
      }
      out.push(closed ? { k: "str", v: s, at: [start, i] } : { k: "bad", v: "a string not closed: \"", at: [start, i] });
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      while (i < src.length && /[A-Za-z0-9_]/.test(src[i])) i++;
      const w = src.slice(start, i);
      out.push({ k: KEYWORDS.has(w) ? "kw" : "name", v: w, at: [start, i] });
      continue;
    }
    const sym = SYMBOLS.find((s) => src.startsWith(s, i));
    if (sym) { out.push({ k: "sym", v: sym, at: [start, i + sym.length] }); i += sym.length; continue; }
    out.push({ k: "bad", v: `no ${JSON.stringify(c)} in the language`, at: [start, i + 1] });
    i++;
  }
  return out;
}

// --- the syntax: terms ------------------------------------------------------------------------------------------
// A term: {e: "lit", t, v} | {e: "hole", why} | {e: "un", op, a} | {e: "bin", op, a, b} | {e: "if", c, a, b}.

const LEVELS = [["||"], ["&&"], ["==", "!=", "<", "<=", ">", ">="], ["++"], ["+", "-"], ["*", "/"]];
const COMPARE = new Set(LEVELS[2]);

/** `src` -> a term. Never fails: what's missing or can't be read is a hole saying why (and what's left over after a
 * whole term, a hole beside it). */
export function parse(src) {
  const ts = tokens(src);
  let i = 0;
  const peek = () => ts[i], next = () => ts[i++];
  const is = (k, v) => ts[i] && ts[i].k === k && (v === undefined || ts[i].v === v);
  const hole = (why) => ({ e: "hole", why });
  function atom() {
    const t = peek();
    if (!t) return hole("an expression to come");
    if (t.k === "num") { next(); return { e: "lit", ...t.v }; }
    if (t.k === "str") { next(); return { e: "lit", t: "String", v: t.v }; }
    if (t.k === "kw" && (t.v === "true" || t.v === "false")) { next(); return { e: "lit", t: "Bool", v: t.v === "true" }; }
    if (t.k === "sym" && t.v === "(") {
      next();
      const inner = expr();
      if (is("sym", ")")) next(); else return { e: "bin", op: "(", a: inner, b: hole("a ) to close it") };
      return { e: "paren", a: inner };
    }
    if (t.k === "kw" && t.v === "if") return cond();
    if (t.k === "name") { next(); return hole(`nothing is called ${t.v} (no names yet)`); }
    if (t.k === "bad") { next(); return hole(t.v); }
    return hole(`an expression, not ${t.v}`);
  }
  function unary() {
    if (is("sym", "-")) { next(); return { e: "un", op: "-", a: unary() }; }
    if (is("kw", "not")) { next(); return { e: "un", op: "not", a: unary() }; }
    return atom();
  }
  function level(n) {
    if (n === LEVELS.length) return unary();
    let a = level(n + 1);
    while (ts[i] && ts[i].k === "sym" && LEVELS[n].includes(ts[i].v)) {
      const op = next().v;
      a = { e: "bin", op, a, b: level(n + 1) };
      if (COMPARE.has(op) && ts[i] && ts[i].k === "sym" && COMPARE.has(ts[i].v)) {   // (a < b < c: compare one pair)
        next();
        level(n + 1);   // (what it was compared with, read past)
        return { e: "after", a, b: hole("one comparison at a time: use && between them") };
      }
    }
    return a;
  }
  function cond() {
    next();   // if
    const c = expr();
    const a = is("kw", "then") ? (next(), expr()) : hole("then …");
    const b = is("kw", "else") ? (next(), expr()) : hole("else …");
    return { e: "if", c, a, b };
  }
  const expr = () => level(0);
  const term = expr();
  if (i < ts.length) {   // (something after a whole term: kept, as a hole beside it)
    const rest = ts.slice(i).map((t) => src.slice(t.at[0], t.at[1])).join(" ");
    return { e: "after", a: term, b: hole(`nothing goes after it: ${rest}`) };
  }
  return term;
}

// --- types --------------------------------------------------------------------------------------------------------
// A type: "Int" | "Float" | "String" | "Bool" | "?" (a hole's: unknown, consistent with any, as Hazel's).

const same = (a, b) => a === "?" || b === "?" || a === b;
const known = (...ts) => ts.find((t) => t !== "?") || "?";

/** Term `term` typed: the same term, each node given its type (`ty`); one that doesn't type marked a hole in its
 * place (`wrong`: why), its type unknown, so nothing around it fails because of it. */
export function check(term) {
  const fail = (node, why) => ({ e: "wrong", a: node, why, ty: "?" });
  function go(n) {
    switch (n.e) {
      case "lit": return { ...n, ty: n.t };
      case "hole": return { ...n, ty: "?" };
      case "paren": { const a = go(n.a); return { ...n, a, ty: a.ty }; }
      case "after": { const a = go(n.a), b = go(n.b); return { ...n, a, b, ty: "?" }; }
      case "un": {
        const a = go(n.a);
        if (n.op === "-") return ["Int", "Float", "?"].includes(a.ty) ? { ...n, a, ty: a.ty } : fail({ ...n, a }, `- needs a number, got ${a.ty}`);
        return same(a.ty, "Bool") ? { ...n, a, ty: "Bool" } : fail({ ...n, a }, `not needs a Bool, got ${a.ty}`);
      }
      case "bin": {
        const a = go(n.a), b = go(n.b), node = { ...n, a, b };
        if (n.op === "(") return { ...node, ty: "?" };
        const both = known(a.ty, b.ty);
        if (!same(a.ty, b.ty)) return fail(node, `${n.op} needs two of one type: ${a.ty} and ${b.ty}`);
        switch (n.op) {
          case "+": case "-": case "*": case "/":
            return ["Int", "Float", "?"].includes(both) ? { ...node, ty: both } : fail(node, `${n.op} needs numbers, got ${both}`);
          case "++":
            return same(both, "String") ? { ...node, ty: "String" } : fail(node, `++ joins Strings, got ${both}`);
          case "==": case "!=":
            return { ...node, ty: "Bool" };
          case "<": case "<=": case ">": case ">=":
            return both !== "Bool" ? { ...node, ty: "Bool" } : fail(node, `${n.op} compares numbers or Strings, not Bools`);
          case "&&": case "||":
            return same(both, "Bool") ? { ...node, ty: "Bool" } : fail(node, `${n.op} needs Bools, got ${both}`);
        }
        return fail(node, `no ${n.op}`);
      }
      case "if": {
        const c = go(n.c), a = go(n.a), b = go(n.b), node = { ...n, c, a, b };
        if (!same(c.ty, "Bool")) return fail(node, `if needs a Bool, got ${c.ty}`);
        if (!same(a.ty, b.ty)) return fail(node, `then and else must be one type: ${a.ty} and ${b.ty}`);
        return { ...node, ty: known(a.ty, b.ty) };
      }
    }
    return fail(n, "can't read this");
  }
  return go(term);
}

// --- evaluation ---------------------------------------------------------------------------------------------------
// A result: {v, t} a value of type t, or {r: text} what's left of the expression around its holes (indeterminate).

/** Typed term `n` (check's) evaluated: a value, or the expression as far as it could be worked out. */
export function evaluate(n) {
  const val = (v, t) => ({ v, t });
  const res = (r) => ({ r });
  const text = (x) => ("r" in x ? x.r : literal(x));
  switch (n.e) {
    case "lit": return val(n.v, n.t);
    case "hole": return res(`⦃${n.why}⦄`);
    case "wrong": return res(`⦃${n.why}⦄`);
    case "paren": { const a = evaluate(n.a); return "r" in a ? res(`(${a.r})`) : a; }
    case "after": return res(`${text(evaluate(n.a))} ${text(evaluate(n.b))}`);
    case "un": {
      const a = evaluate(n.a);
      if ("r" in a) return res(`${n.op === "not" ? "not " : "-"}${a.r}`);
      return n.op === "not" ? val(!a.v, "Bool") : val(-a.v, a.t);
    }
    case "if": {
      const c = evaluate(n.c);
      if ("r" in c) return res(`if ${c.r} then ${text(evaluate(n.a))} else ${text(evaluate(n.b))}`);
      return evaluate(c.v ? n.a : n.b);   // (only the branch taken: a hole in the other doesn't matter)
    }
    case "bin": {
      if (n.op === "&&" || n.op === "||") {   // (short-circuit, as you'd expect: false && ⦃…⦄ is false)
        const a = evaluate(n.a);
        if (!("r" in a) && a.v === (n.op === "||")) return a;
        const b = evaluate(n.b);
        if ("r" in a || "r" in b) return res(`${text(a)} ${n.op} ${text(b)}`);
        return b;
      }
      const a = evaluate(n.a), b = evaluate(n.b);
      if (n.op === "(") return res(`(${text(a)} ${text(b)}`);
      if ("r" in a || "r" in b) return res(`${text(a)} ${n.op} ${text(b)}`);
      switch (n.op) {
        case "+": return val(fix(a.v + b.v, a.t), a.t);
        case "-": return val(fix(a.v - b.v, a.t), a.t);
        case "*": return val(fix(a.v * b.v, a.t), a.t);
        case "/":
          if (b.v === 0) return res(`${literal(a)} / ${literal(b)} ⦃can't divide by zero⦄`);
          return val(a.t === "Int" ? Math.trunc(a.v / b.v) : a.v / b.v, a.t);
        case "++": return val(a.v + b.v, "String");
        case "==": return val(a.v === b.v, "Bool");
        case "!=": return val(a.v !== b.v, "Bool");
        case "<": return val(a.v < b.v, "Bool");
        case "<=": return val(a.v <= b.v, "Bool");
        case ">": return val(a.v > b.v, "Bool");
        case ">=": return val(a.v >= b.v, "Bool");
      }
    }
  }
  return res("⦃can't work this out⦄");
}

/** Ints stay whole (Int arithmetic is exact, as JS numbers are to 2^53). */
const fix = (v, t) => (t === "Int" ? Math.trunc(v) : v);

/** A value as code would write it: a String quoted, a Float with its point. */
export function literal({ v, t }) {
  if (t === "String") return JSON.stringify(v);
  if (t === "Float") return Number.isInteger(v) ? v.toFixed(1) : String(v);
  return String(v);
}

/** A value cast to text, as a block shows it (for now every block shows text): a String its text, unquoted. */
export function show({ v, t }) {
  return t === "String" ? v : literal({ v, t });
}

/** Source `src`, all the way: {text: what the block shows, type: its type ("?" when unfinished), done: a value (no
 * holes)}. An empty one shows nothing yet. */
export function run(src) {
  if (!src.trim()) return { text: "", type: "?", done: false, empty: true };
  const typed = check(parse(src));
  const out = evaluate(typed);
  return "r" in out ? { text: out.r, type: typed.ty, done: false } : { text: show(out), type: out.t, done: true };
}
