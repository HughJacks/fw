// fixture.mjs — what the browser scenarios share: the store each starts from (its blocks' ids), and helpers.
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const A = "20261001T100000-a000", A1 = "20261001T100000-a001", QA = "20261001T100000-a002";
export const B = "20261002T100000-b000", B1 = "20261002T100000-b001";
export const T = "20261003T100000-c000", T1 = "20261003T100000-c001", T2 = "20261003T100000-c002";
export const M = "20261004T100000-d000", QM = "20261004T100000-d001";
export const R = "20261005T100000-e000", R1 = "20261005T100000-e001", QR1 = "20261005T100000-e002", QR2 = "20261005T100000-e003";
export const blk = (id, content, title = null) => ({ id, title, content, words: 0, created: "2026-10-01T10:00:00-04:00" });
export const K = "20261006T100000-f000";   // a kind, "poem" (its description empty)
export const N = "20261008T100000-b100", QN = "20261008T100000-b101", N1 = "20261008T100000-b102";   // a quote of alpha (which quotes beta): a quote inside a quote
export const S0 = "20261007T100000-a100", S1 = "20261007T100000-a101", S2 = "20261007T100000-a102";   // a container holding one block
export const STORE = { schemaVersion: 9, entries: [A, B, T, M, R, K, S0, N], blocks: [
  blk(N, [QN, N1], "nested"), blk(QN, { quote: A }), blk(N1, "after the quotes"),
  blk(S0, [S1], "one inside"), blk(S1, [S2]), blk(S2, "the only block inside"),
  blk(K, { kind: "poem", blocks: [] }),
  blk(A, [A1, QA], "alpha"), blk(A1, "first words"), blk(QA, { quote: B }),
  blk(B, [B1], "beta"), blk(B1, "beta's words"),
  blk(T, [T1, T2], "fox"), blk(T1, "the quick brown fox"), blk(T2, "jumps over the dog"),
  blk(M, [QM], "masker"), blk(QM, { quote: T }),
  blk(R, [R1, QR1, QR2], "two quotes"), blk(R1, "r words"), blk(QR1, { quote: B }), blk(QR2, { quote: T })] };

/** The store's .json copy in `dir`, once it's caught up with the document (the core writes it a moment after its
 * last save: store.json_later). */
export async function storedIn(dir) {
  const mtime = (f) => { try { return statSync(join(dir, f)).mtimeMs; } catch { return 0; } };
  for (let n = 0; n < 60 && mtime("freewrites.json") < mtime("freewrites.loro"); n++) await sleep(50);
  return JSON.parse(readFileSync(join(dir, "freewrites.json"), "utf8"));
}

/** The open code box's text set to `src` (CodeMirror's own change: told back to the block as typing is). */
export const setCode = (t, src) => t.js(`(() => { const v = document.querySelector(".fw-expr-codebox").fwCode;
  v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: ${JSON.stringify(src)} } }); return 1; })()`);

/** An expression block put in at the end of the open pericope, its code `src`, then shown at rest (⌘⇧X). */
export async function addExpr(t, src) {
  await t.end();
  await t.key("Enter");
  await t.type("/");
  await t.type("expr");
  await t.until(`!!document.querySelector(".fw-slash, .fw-menu")`, 2000);
  await t.key("Enter");
  await t.until(`!!document.activeElement?.closest(".fw-expr-code")`, 2000);
  await setCode(t, src);
  await t.key("x", 4 | 8);
  await t.until(`!document.querySelector(".fw-expr-code")`, 2000);
  await t.settle();
}

export const lastOut = `[...document.querySelectorAll(".fw-doc .fw-expr > .fw-expr-out")].at(-1)`;

/** Another window on the same core (the user's two windows): its own tab, at `hash`. */
export async function window2(t, hash) {
  const w = await t.tab();
  const js = async (e) => (await w.cdp("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
  const until = async (e, ms = 4000) => { for (const end = Date.now() + ms; Date.now() < end; await sleep(25)) if (await js(e)) return true; return false; };
  const id = hash.match(/^#\/p\/([^@]+)/)[1];
  await w.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test${hash}` });
  await until(`window.fw?.editor()?.id === "${id}"`, 6000);
  await until(`window.fw?.settled()`);
  return { js, until, close: w.close, type: (text) => w.cdp("Input.insertText", { text }),
    select: (text, o = {}) => js(`window.fw.select(${JSON.stringify(text)}, ${JSON.stringify(o)})`),
    async key(k, mods = 0) {
      const p = { key: k, code: `Key${k.toUpperCase()}`, windowsVirtualKeyCode: k.toUpperCase().charCodeAt(0), modifiers: mods };
      await w.cdp("Input.dispatchKeyEvent", { type: "rawKeyDown", ...p }); await w.cdp("Input.dispatchKeyEvent", { type: "keyUp", ...p });
    } };
}
