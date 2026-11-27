import { join } from "node:path";
import { writeFileSync } from "node:fs";
import { A, B, B1, M, N, QA, QM, QN, R, T, sleep, window2 } from "./fixture.mjs";

export const scenarios = {};

scenarios.masking = async (t) => {
  await t.open(`#/p/${M}@${QM}`);
  await t.key("M", 12);   // ⌘⇧M: masking
  t.check("⌘⇧M on a quote: masking, its whole text", await t.until(`document.querySelector(".fw-masking")?.innerText.includes("jumps over the dog")`, 3000));
  await t.js(`(() => {   // "quick brown" selected in the masking view (not ProseMirror: the page's own selection)
    const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("the quick brown fox"));
    const x = piece.firstChild, at = x.textContent.indexOf("quick");
    const r = document.createRange(); r.setStart(x, at); r.setEnd(x, at + "quick brown".length);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
  const caret = `(() => { const s = window.getSelection(); return s.focusNode?.parentElement?.closest(".fw-masking") ? s.focusNode.parentElement.textContent + "|" + s.focusOffset : null; })()`;
  await t.key("ArrowDown");
  const down = await t.js(caret);
  t.check("  ↓ moves the caret in masking (the page doesn't take it), still masking", down && !down.startsWith("the quick brown fox") && await t.js(`!!document.querySelector(".fw-masking")`), down);
  await t.key("ArrowUp");
  t.check("  ↑ back", (await t.js(caret))?.startsWith("the quick brown fox"), await t.js(caret));
  const at = await t.js(`(() => { const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("jumps over"));
    const r = document.createRange(); r.setStart(piece.firstChild, 6); r.setEnd(piece.firstChild, 7); const b = r.getBoundingClientRect(); return [b.left + 1, b.top + b.height / 2]; })()`);
  await t.click(at[0], at[1]);
  await t.settle();
  t.check("  a click in its text: the caret there, still masking", await t.js(`!!document.querySelector(".fw-masking")`) && (await t.js(caret))?.startsWith("jumps over"), await t.js(caret));
  await t.js(`(() => {   // "quick brown" selected again
    const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("the quick brown fox"));
    const x = piece.firstChild, at = x.textContent.indexOf("quick");
    const r = document.createRange(); r.setStart(x, at); r.setEnd(x, at + "quick brown".length);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
  const qx = `(() => { const w = document.createTreeWalker(document.querySelector(".fw-masking"), NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) { const i = n.data.indexOf("quick"); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 1); return Math.round(r.getBoundingClientRect().left); } } })()`;
  const before = await t.js(qx);
  await t.key("[");
  t.check("  marking never moves the text (the brackets take no room)", await t.until(`document.querySelectorAll(".fw-masking .fw-br").length === 2`, 2000) && (await t.js(qx)) === before,
    JSON.stringify([before, await t.js(qx)]));
  t.check("  [ on a selection: just it shows, the rest dim, in brackets", await t.until(`[...document.querySelectorAll(".fw-masking .fw-shown")].map(s => s.textContent).join("") === "quick brown"
    && document.querySelectorAll(".fw-masking .fw-br").length === 2`, 2000), await t.js(`document.querySelector(".fw-masking")?.innerText`));
  await t.key("Escape");
  await t.settle();
  const q = (await t.kids(M))[0], shown = q.body.map((b) => b.text).join(" ");
  t.check("  Esc: finished, the mask saved; the quote shows just that", q.masked && shown.includes("quick brown") && !shown.includes("jumps"), JSON.stringify(q.body));
  t.check("    drawn so: …quick brown…", await t.until(`document.querySelector(".fw-doc .fw-quote")?.innerText.includes("quick brown") && document.querySelector(".fw-doc .fw-quote").innerText.includes("…")`, 2000));
  const r0 = await t.js("window.fw.reloads || 0");
  t.check("(the cursor after \"brown\", in the quote)", await t.select("brown", { collapse: true }), "reloads " + r0 + " " + await t.js("window.fw.reloads || 0") + " " + await t.js(`document.querySelector(".fw-doc").innerText`));
  await t.type(" red");   // (written through the mask, the lens)
  await t.settle();
  const tk = await t.kids(T);
  t.check("  written through the mask: the source changed, what's hidden kept", tk[0].text === "the quick brown red fox" && tk[1].text === "jumps over the dog", JSON.stringify(tk.map((c) => c.text)));
  await t.js(`window.fw.editor().view.focus(); 1`);
  await t.key("z", 4);
  await t.settle();
  t.check("  ^Z (in the pericope): the mask taken back", !(await t.kids(M))[0].masked);
  await t.shot("masking.png");
};

scenarios.maskNested = async (t) => {   // a quote inside the quote being masked: drawn in full while masking, and after (not a stand-in)
  await t.open(`#/p/${N}@${QN}`);
  await t.key("M", 12);
  t.check("masking a quote that holds a quote: the inner one drawn in full", await t.until(`!!document.querySelector(".fw-masking .fw-quote.fw-unit")?.innerText.includes("beta's words")`, 3000),
    await t.js(`document.querySelector(".fw-masking")?.innerText`));
  await t.js(`(() => { const piece = [...document.querySelectorAll(".fw-masking [data-off]")].find(s => s.textContent.includes("first words"));
    const x = piece.firstChild, r = document.createRange(); r.setStart(x, 0); r.setEnd(x, "first".length);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); return true; })()`);
  await t.key("]");   // ("first" hidden; the rest, the quote inside too, shown)
  await t.key("Escape");
  await t.settle();
  t.check("  masked: the quote inside still drawn in full, as a quote (not a one-line stand-in)",
    await t.until(`!!document.querySelector(".fw-doc .fw-quote .fw-quote")?.innerText.includes("beta's words") && !document.querySelector(".fw-rawline")`, 2000),
    await t.js(`document.querySelector(".fw-doc .fw-quote")?.innerText`));
};

scenarios.topline = async (t) => {   // a quote's top line: a mini header of what it shows of its source
  await t.open(`#/p/${A}`);
  const top = `document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-top-label")`;
  t.check("a quote showing nothing on its top line: no mini header", await t.js(`${top}.childElementCount === 0`));
  await fetch(`http://127.0.0.1:${t.port}/api/act`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ do: "show", quote: QA, show: ["title", "words", "updated"] }) });
  await t.open(`#/p/${B}`); await t.open(`#/p/${A}`);
  t.check("  showing its title, words, last update: a line of facts, then its title", await t.until(
    `${top}.querySelector(".fw-mini-title")?.textContent === "beta" && /^words \\d+ · updated /.test(${top}.querySelector(".fw-mini-facts")?.textContent)`, 2000),
    await t.js(`${top}.innerText`));
  t.check("  its title the header title's font and size, the writing's size", await t.js(`(() => { const a = getComputedStyle(${top}.querySelector(".fw-mini-title")),
    b = getComputedStyle(document.querySelector(".fw-title")), w = getComputedStyle(document.querySelector(".fw-text, .fw-doc p") || document.body);
    return a.fontSize === b.fontSize && a.fontWeight === b.fontWeight && a.fontFamily === b.fontFamily && a.fontSize === w.fontSize; })()`));
  await t.shot("topline.png");
  // toggled from the menu's submenu (the user: each toggle kicked us out of the submenu and moved the cursor)
  await t.select("beta's", { collapse: true }); await t.settle();
  const caret = `(() => { const s = getSelection(), n = s.anchorNode; return n ? [n.textContent, s.anchorOffset, !!n.parentElement?.closest(".fw-quote")].join("|") : ""; })()`;
  const before = await t.js(caret);
  await t.key("/", 4);
  await t.until(`document.querySelector(".fw-menu")?.innerText.includes("Its top line")`, 1000);
  const down = await t.js(`[...document.querySelectorAll(".fw-menu .fw-row")].findIndex((r) => r.innerText.startsWith("Its top line"))`);
  for (let n = 0; n < down; n++) await t.key("ArrowDown");
  await t.key("ArrowRight");   // (into the submenu)
  await t.until(`document.querySelector(".fw-menu")?.innerText.includes("its date")`, 1000);
  const rows = `[...document.querySelectorAll(".fw-menu .fw-row")].map((r) => r.innerText.split("\\n")[0]).join(",")`;
  await t.js(`window.__left = 0; document.querySelector(".fw-menu input").addEventListener("blur", () => window.__left++); 1`);
  await t.key("Enter");   // (the first: Hide its title)
  await t.settle();
  t.check("  a toggle in the submenu: the menu still open, still the submenu, saying what's on now", await t.until(
    `document.querySelector(".fw-menu") && ${rows}.startsWith("Show its title,")`, 2000), await t.js(rows));
  await t.key("ArrowDown"); await t.key("Enter");   // Show its date
  await t.settle();
  t.check("  another: still there, the next toggled", await t.until(`document.querySelector(".fw-menu") && ${rows}.includes("Hide its date")`, 2000), await t.js(rows));
  t.check("  the focus never left the menu (a slow store would close it)", (await t.js(`window.__left`)) === 0, String(await t.js(`window.__left`)));
  t.check("  the store has both", JSON.stringify((await t.kids(A))[1].show) === JSON.stringify(["created", "updated", "words"]), JSON.stringify((await t.kids(A))[1].show));
  await t.key("Escape"); await t.key("Escape");
  await t.settle();
  t.check("  the menu closed: the cursor where it was", (await t.js(caret)) === before, `${await t.js(caret)} (was ${before})`);
  // nested, recursive: a quote's mini header joined to its first block; quiet at rest
  // (the user: "the header border and glow only shows up when selected or adjacent"): its border unseen
  // but when the quote is selected whole or its first block is the active one, each quote's own, at any depth
  await fetch(`http://127.0.0.1:${t.port}/api/act`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ do: "show", quote: QN, show: ["title", "words"] }) });
  await t.open(`#/p/${B}`); await t.open(`#/p/${N}`);
  const line = (sel) => `(() => { const l = document.querySelector('${sel}'); return !!l && getComputedStyle(l, "::after").content !== "none"; })()`;
  const outer = `.fw-doc > .ProseMirror > .fw-quote > .fw-top > .fw-top-label`, inner = `.fw-doc .fw-quote .fw-quote > .fw-top > .fw-top-label`;
  // how its box is drawn: "unseen", "glow <colour>" (its bottom edge, a neighbour's), "box <colour>"; and where its text is
  const look = (sel) => `(() => { const top = document.querySelector('${sel}').parentElement, cs = getComputedStyle(top);
    const r = top.firstElementChild.getBoundingClientRect(), at = [r.left, r.top].map(Math.round).join(",");
    if (cs.borderImageSource !== "none") return "glow " + cs.getPropertyValue("--lit-down").trim() + " @" + at;
    return (cs.borderTopColor === "rgba(0, 0, 0, 0)" ? "unseen" : "box " + cs.borderTopColor) + " @" + at; })()`;
  const root = (v) => t.js(`(() => { const e = document.createElement("i"); e.style.color = "var(${v})"; document.body.append(e);
    const c = getComputedStyle(e).color; e.remove(); return c; })()`);   // (as the glow's registered colour computes: rgb(…))
  const [hi, fg] = [await root("--box-hi"), await root("--fg")];
  const kind = (s) => s.split(" @")[0], where = (s) => s.split(" @")[1];
  await t.select("after the", { collapse: true }); await t.settle();
  const rest = [await t.js(look(outer)), await t.js(look(inner))];
  t.check("  at rest: the small headers' boxes unseen, no line to their blocks", rest.every((s) => kind(s) === "unseen")
    && !(await t.js(line(outer))) && !(await t.js(line(inner))), rest.join(" | "));
  await t.shot("topline-rest.png");
  await t.select("first wo", { collapse: true }); await t.settle();
  let now = [await t.js(look(outer)), await t.js(look(inner))];
  t.check("  in a quote's first block (adjacent): its bottom edge glows as a neighbour's, its line drawn; not the quote's inside it",
    kind(now[0]) === `glow ${hi}` && kind(now[1]) === "unseen" && await t.js(line(outer)) && !(await t.js(line(inner))), now.join(" | "));
  t.check("  nothing moves as it lights", where(now[0]) === where(rest[0]), `${where(now[0])} (at rest ${where(rest[0])})`);
  await t.shot("topline-adjacent.png");
  await t.select("beta's", { collapse: true }); await t.settle();
  now = [await t.js(look(outer)), await t.js(look(inner))];
  t.check("  in the quote inside it (recursive): that one's, not the outer's (in it, not beside its header: unseen)",
    kind(now[1]) === `glow ${hi}` && kind(now[0]) === "unseen" && await t.js(line(inner)) && !(await t.js(line(outer))), now.join(" | "));
  t.check("  its box a block's, its text on the blocks' column, the line from it reaching the first block", await t.js(`(() => {
    const top = document.querySelector('${inner}').parentElement, q = top.parentElement, l = top.firstElementChild;
    const tb = top.getBoundingClientRect(), lb = l.getBoundingClientRect(), after = getComputedStyle(l, "::after");
    const first = q.querySelector(":scope > .fw-body > .ProseMirror > *"), fb = first.getBoundingClientRect();
    const tx = first.querySelector(".fw-text, p") || first, range = document.createRange(); range.selectNodeContents(tx);
    const textX = range.getClientRects()[0].left, lineTop = lb.top + parseFloat(after.top), lineBot = lineTop + parseFloat(after.height);
    return getComputedStyle(top).borderTopStyle === "solid" && Math.abs(lb.left - textX) < 1.5 && Math.abs(lineTop - tb.bottom) < 1.5 && Math.abs(lineBot - fb.top) < 1.5; })()`));
  t.check("  both titles in the body's weight", await t.js(`getComputedStyle(document.querySelector(".fw-title")).fontWeight === getComputedStyle(document.body).fontWeight
    && getComputedStyle(document.querySelector(".fw-mini-title")).fontWeight === getComputedStyle(document.body).fontWeight`));
  await t.shot("topline-nested.png");
  await t.select("first wo", { collapse: true }); await t.key("Escape"); await t.settle();
  now = [await t.js(look(outer)), await t.js(look(inner))];
  t.check("  its first block selected whole: the glow bright, as beside any block selected whole",
    kind(now[0]) === `glow ${fg}` && kind(now[1]) === "unseen" && await t.js(line(outer)), now.join(" | "));
  await t.key("Escape"); await t.settle();   // (Esc again: out to the quote, selected whole)
  await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-quote.fw-chosen")`, 1000);
  now = [await t.js(look(outer)), await t.js(look(inner))];
  t.check("  the quote selected whole: its mini header's box shown, its line drawn; the one inside it its own (unseen)",
    kind(now[0]) === `box ${await t.js(`getComputedStyle(document.querySelector('${outer}').parentElement).borderTopColor`)}` && kind(now[0]) !== "unseen"
    && kind(now[1]) === "unseen" && await t.js(line(outer)) && where(now[0]) === where(rest[0]), now.join(" | "));
  await t.shot("topline-selected.png");
};

scenarios.onebox = async (t) => {   // a quote showing one block draws one box: the block's own (its border-image too) never shows
  await t.open(`#/p/${A}`);
  const inner = `getComputedStyle(document.querySelector(".fw-quote > .fw-body .fw-text")).borderImageSource`;
  t.check("a quote of a pericope of one block, at rest: no box inside", await t.js(`${inner} === "none"`), await t.js(inner));
  await t.select("beta's words"); await t.settle();
  t.check("  in it: still none (the glow's gradient off too)", await t.js(`${inner} === "none" && document.querySelector(".fw-quote > .fw-body .fw-text.fw-here") !== null`), await t.js(inner));
  await t.key("Escape"); await t.settle();
  t.check("  selected whole: none", await t.js(`${inner} === "none" && !!document.querySelector(".fw-quote.fw-chosen")`), await t.js(inner));
};

scenarios.arrowFlow = async (t) => {   // the arrows flow through quotes inside quotes, going into each (never selected whole on the way)
  // (nested: a quote of alpha [first words, a quote of beta [beta's words]], then "after the quotes")
  const at = `(() => { const ch = document.querySelector(".fw-chosen"); const short = (x) => (x || "").replace(/\\s+/g, " ").trim();
    if (ch) return "whole:" + short(ch.querySelector(".fw-qtext, .fw-text")?.textContent);
    return "text:" + short(window.getSelection().focusNode?.textContent); })()`;
  const walk = async (key, n) => { const out = []; for (let k = 0; k < n; k++) { await t.key(key); await t.settle(); out.push(await t.js(at)); } return out; };
  await t.open(`#/p/${N}`);
  await t.select("after the quotes", { collapse: true, start: true });
  const up = await walk("ArrowUp", 2);
  t.check("↑ from below: into the outer quote and on into the inner, at its end; then the outer's text (gone into, not selected whole)",
    JSON.stringify(up) === JSON.stringify(["text:beta's words", "text:first words"]), JSON.stringify(up));
  await t.key("ArrowUp");
  t.check("  ↑ out of the page's first quote: the header's title, as from text", await t.until(`!!document.activeElement?.matches(".fw-title")`, 1000));
  await t.select("first words", { collapse: true });
  const down = await walk("ArrowDown", 2);
  t.check("↓ back: into the inner quote's text, then out of both (nothing after them inside) to what's below",
    JSON.stringify(down) === JSON.stringify(["text:beta's words", "text:after the quotes"]), JSON.stringify(down));
  await t.select("beta's words", { collapse: true });
  const esc = await walk("Escape", 2);
  t.check("Esc steps out a level each time: the inner quote (its one block is its box), then the outer",
    JSON.stringify(esc) === JSON.stringify(["whole:beta's words", "whole:first words"]), JSON.stringify(esc));
};

scenarios.twowindows = async (t) => {   // two windows on one store: a source in one, a pericope quoting it in the other
  const other = await t.tab();
  const ojs = async (e) => (await other.cdp("Runtime.evaluate", { expression: e, returnByValue: true, awaitPromise: true })).result?.result?.value;
  await other.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test#/p/${B}` });
  for (let n = 0; n < 200 && !(await ojs(`window.fw?.editor()?.id === "${B}"`)); n++) await sleep(25);
  await t.open(`#/p/${R}`);
  const quoted = `[...document.querySelectorAll(".fw-quote")].map((q) => q.textContent).join(" | ")`;
  await ojs(`window.fw.select("beta's words", { collapse: true })`);
  const t0 = Date.now();
  await other.cdp("Input.insertText", { text: " LIVE" });
  const seen = await t.until(`(${quoted}).includes("LIVE")`, 5000);
  t.check(`typed in the source: the quote in the other window follows (${Date.now() - t0} ms)`, seen, await t.js(quoted));
  await t.settle();
  await t.select("beta's words LIVE", { collapse: true });
  const t1 = Date.now();
  await t.type(" BACK");
  const back = await (async () => { for (const end = Date.now() + 5000; Date.now() < end; await sleep(25)) if ((await ojs(`document.querySelector(".fw-doc").textContent`))?.includes("LIVE BACK")) return true; return false; })();
  t.check(`typed through the quote: the source's window follows (${Date.now() - t1} ms)`, back, await ojs(`document.querySelector(".fw-doc").textContent`));
  // (then back in the source's window: the quote, written through a moment ago, its caret still in it, follows too)
  await ojs(`window.fw.select("LIVE BACK", { collapse: true })`);
  const t2 = Date.now();
  await other.cdp("Input.insertText", { text: " AGAIN" });
  const again = await t.until(`(${quoted}).includes("BACK AGAIN")`, 5000);
  t.check(`after writing through it: the source edited elsewhere, the quote follows (${Date.now() - t2} ms)`, again, await t.js(quoted));
  other.close();
};

// Live: every view of a block follows it, wherever it was written ("this a is a very fundamental
// idea… not just in this case but in every case… its about live enviroments and dependencies"). Each case: the source
// written in one window, what depends on it seen in another.
const LX = "20261009T100000-c100", LXQ = "20261009T100000-c101", LXE = "20261009T100000-c102";

scenarios.live = async (t) => {
  const text = (sel) => `[...document.querySelectorAll(${JSON.stringify(sel)})].map((q) => q.textContent).join(" | ")`;
  const src = await window2(t, `#/p/${B}`);   // beta, the source, in a window of its own
  const step = async (label, write, seen, detail) => {
    const t0 = Date.now();
    await write();
    const ok = await t.until(seen, 5000);
    t.check(`${label} (${Date.now() - t0} ms)`, ok, await t.js(detail));
  };

  // a quote inside a quote: nested (N quotes alpha, which quotes beta)
  await t.open(`#/p/${N}`);
  await src.select("beta's words", { collapse: true });
  await step("a quote of a quote: the source written, the nested quote follows", () => src.type(" one"),
    `(${text(".fw-quote")}).includes("words one")`, text(".fw-quote"));

  // a masked quote: what shows grows with what's written inside it
  await t.open(`#/p/${LX}`);
  await src.select("beta", { collapse: true });
  await step("a masked quote: written inside what shows, it follows", () => src.type("X"),
    `(${text(".fw-quote")}).includes("betaX's")`, text(".fw-quote"));
  // an expression reading it
  const was = await t.js(text(".fw-expr"));
  await src.select("words one", { collapse: true });
  await step("an expression reading it: its value follows", () => src.type(" two three"),
    `(${text(".fw-expr")}) !== ${JSON.stringify(was)}`, text(".fw-expr"));

  // the caret in the quote, carried: written elsewhere before it, then typing here goes where it was
  await t.open(`#/p/${R}`);
  await t.select("two three", { collapse: true });
  await src.select("betaX's", { collapse: true, start: true });
  await step("the caret in a quote, the source written before it elsewhere: followed", () => src.type("AT START "),
    `(${text(".fw-quote")}).includes("AT START")`, text(".fw-quote"));
  await t.type("!");
  await t.settle();
  const b1 = async () => (await t.kids(B))[0].text;
  t.check("  typing here after it: where the caret was (carried, not reset)", (await b1()) === "AT START betaX's words one two three!", await b1());

  // undo here takes back only what was written here, never what came from elsewhere
  await t.select("r words", { collapse: true });
  await t.type(" mine");
  await t.settle();
  await src.until(`document.querySelector(".fw-doc").textContent.includes("three!")`);   // (the source's window has it: then its caret goes there)
  await src.select("three!", { collapse: true });
  await step("  written here, then the source elsewhere: followed", () => src.type(" theirs"),
    `(${text(".fw-quote")}).includes("theirs")`, text(".fw-quote"));
  await t.select("r words mine", { collapse: true });
  await t.key("z", 4);
  await t.settle();
  const r1 = (await t.kids(R))[0].text;
  t.check("  ⌘Z here: only what was written here taken back", r1 === "r words" && (await b1()).endsWith("theirs"), JSON.stringify([r1, await b1()]));

  // the same pericope in both windows: each follows the other, the caret carried
  await t.open(`#/p/${B}`);
  await t.select("AT START", { collapse: true });
  await src.until(`document.querySelector(".fw-doc").textContent.includes("theirs")`);
  await src.select("AT", { collapse: true, start: true });
  await step("the same pericope in two windows: written in one, the other follows", () => src.type(">> "),
    `document.querySelector(".fw-doc").textContent.includes(">> AT START")`, `document.querySelector(".fw-doc").textContent`);
  await t.type("|");
  await t.settle();
  t.check("  and its caret carried", (await b1()).startsWith(">> AT START|"), await b1());

  // both at once, the same block: neither refused, neither lost, and both windows end up saying the same
  await t.select("AT START|", { collapse: true });
  await src.until(`document.querySelector(".fw-doc").textContent.includes("AT START|")`);
  await src.select("three!", { collapse: true });
  await Promise.all([t.type(" HERE"), src.type(" THERE")]);
  const both = `(() => { const x = document.querySelector(".fw-doc").textContent; return x.includes(" HERE") && x.includes(" THERE"); })()`;
  const merged = await t.until(both, 5000) && await src.until(both, 5000);
  await t.settle();
  t.check("both windows writing the same block at once: merged, both kept, in both windows", merged && (await b1()).includes(" HERE") && (await b1()).includes(" THERE"),
    JSON.stringify([await b1(), await t.js(`document.querySelector(".fw-doc").textContent`), await src.js(`document.querySelector(".fw-doc").textContent`)]));
  t.check("  and neither window is stuck (nothing unsaved, nothing refused)", await t.until(`!window.fw.editor().dirty()`) && await src.until(`!window.fw.editor().dirty() && !/not saved/.test(window.fw.editor().message)`),
    await src.js(`window.fw.editor().message`));
  src.close();
};

scenarios.live.setup = (dir, data) => {   // a pericope with a masked quote of beta (just "beta's") and an expression reading beta
  const like = (id, content, extra = {}) => ({ ...data.blocks.find((b) => b.id === B1), id, content, title: null, ...extra });
  data.blocks.push(like(LX, [LXQ, LXE], { entry: true, title: "watcher" }),
    like(LXQ, { quote: B, mask: { [B1]: [[0, 6]] } }), like(LXE, { expr: `wordCount(@${B})` }));
  writeFileSync(join(dir, "freewrites.json"), JSON.stringify(data));
};
