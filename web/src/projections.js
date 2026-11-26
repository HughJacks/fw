// projections.js — what can be projected from a thing, `x.f` (TYPE.md "Projection": `x.f` is written for `f(x)`, the
// engine rewriting it, fwbridge's `projections`). Completion after a dot, in the code box (codebox.js) and in an inline
// expression's open code (inlinecode.js): fw's functions whose first argument fits what's before the dot first (its type
// as the engine says it, statically: a hole, `this`, a block not saved yet all have one), then the rest. Pure, but for
// asking the engine a type (typeOf, given its run).

/** The receiver of a dot at `dot` in `text`: the postfix chain just before it (a name, an @reference, a call's
 * parentheses, a list's brackets, a string, more dots), "" if there's none. */
export function receiverBefore(text, dot) {
  let i = dot, depth = 0;
  while (i > 0) {
    const c = text[i - 1];
    if (c === ")" || c === "]") { depth++; i--; continue; }
    if (c === "(" || c === "[") { if (!depth) break; depth--; i--; continue; }
    if (c === '"') {   // (a string: back to its opening quote)
      let j = i - 2;
      while (j >= 0 && !(text[j] === '"' && text[j - 1] !== "\\")) j--;
      i = Math.max(j, 0);
      continue;
    }
    if (depth) { i--; continue; }
    if (/[A-Za-z0-9_'@.?]/.test(c)) { i--; continue; }
    if (c === "-" && /[0-9]/.test(text[i - 2] || "") && /[0-9a-f]/.test(text[i] || "")) { i--; continue; }   // (inside an @id)
    break;
  }
  return text.slice(i, dot).trim();
}

/** A function's first argument's type from its signature ("Ref -> Int": Ref; "(Date, Date) -> Bool": Date; Hazel's
 * list functions, no signature given: any list); not a function: null. */
export function firstArg(name, detail) {
  if (["map", "filter", "length"].includes(name)) return "[a]";
  if (!/->/.test(detail || "")) return null;
  const m = detail.match(/^\(([^,()]+(?:\([^()]*\))?)\s*,/) || detail.match(/^([^-]+?)\s*->/);
  return m ? m[1].trim() : null;
}

const fits = (type, arg) => !!type && (arg === type || (arg === "[a]" && /^\[.*\]$/.test(type)));

/** The functions of `builtins` ([[name, signature, note]], codebox.js's BUILTINS) projectable from a value of `type`
 * (null: not known), those whose first argument fits it first: [{label, detail, info, fits}]. */
export function projectionsFor(builtins, type) {
  const fns = builtins.map(([label, detail, info]) => ({ label, detail, info, arg: firstArg(label, detail) })).filter((f) => f.arg);
  const out = fns.map((f) => ({ label: f.label, detail: f.detail || "", info: f.info || "", fits: fits(type, f.arg) }));
  return [...out.filter((f) => f.fits), ...out.filter((f) => !f.fits)];
}

/** `src`'s type as the engine (`run`: hazel.js's) says it ("Ref", "[Ref]", "Date", "Block" …), or null (not loaded,
 * can't parse). */
export function typeOf(run, src) {
  const r = run(src);
  if (!r || r.kind === "error" || r.kind === "empty") return null;
  return r.kind === "block" ? "Block" : r.type || null;
}

/** Whether a dot ends text that can be projected from: a receiver that isn't a bare number (`1.5` is a number). */
export const projectable = (x) => !!x && !/^[0-9]+$/.test(x);
