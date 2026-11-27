import { A, A1, B, N, R, S0, T, T1, T2, sleep } from "./fixture.mjs";

export const scenarios = {};

scenarios.spread = async (t) => {   // (motion on: ?motion) the room round the block you're in eases out, its tab on it throughout
  await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
  await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
  await t.select("first words", { collapse: true });
  await t.key("Enter");   // (a new block below, the one you're in)
  await t.until(`document.querySelector(".fw-tab-focus")?.textContent === "2"`, 2000); await t.settle();
  const sample = `(() => { const h = document.querySelector(".fw-here"), tab = document.querySelector(".fw-tab-focus");
    return h && tab ? [parseFloat(getComputedStyle(h).paddingTop), parseFloat(tab.style.top), h.getBoundingClientRect().top - tab.offsetParent.getBoundingClientRect().top,
      h.getBoundingClientRect().bottom - tab.offsetParent.getBoundingClientRect().top, tab.offsetHeight, h.innerText.includes("first words")] : null; })()`;
  // (the new block's room all there, and its tab come to rest)
  await t.until(`(() => { const s = ${sample}; if (!s) return false; const was = window.__top; window.__top = s; return !!was && was[0] === s[0] && was[1] === s[1]; })()`, 3000);
  const full = (await t.js(sample))[0], rest = 1.6;   // (the room round the block you're in, all there; .1rem at rest)
  // (recorded in the page, a sample each frame, so a busy machine can't make the test miss the motion)
  await t.js(`window.__rec = []; (function rec() { const s = ${sample}; if (s) window.__rec.push(s); if (window.__rec.length < 400) window.__recFrame = requestAnimationFrame(rec); })(); 1`);
  // (ProseMirror takes a caret landing on the page's very start within 200 ms of focus for the browser resetting it, and
  // puts it back: the up below lands there)
  await sleep(250);
  await t.key("ArrowUp");   // (into the block above: its room eases out, the tab goes up with it)
  await t.until(`(() => { const r = window.__rec.filter((s) => s[5]); return r.length > 2 && r.at(-1)[0] === ${full} && r.at(-1)[1] === r.at(-2)[1] && r.at(-2)[1] === r.at(-3)[1]; })()`, 4000);
  await t.js(`cancelAnimationFrame(window.__recFrame); 1`);
  const seen = (await t.js(`window.__rec`)).filter((s) => s[5]);
  const pads = seen.map((s) => s[0]), tops = seen.map((s) => s[1]), last = seen.at(-1);
  t.check("moving to another block: its room eases out (between at rest and full, on the way)", pads.some((v) => v > rest + 0.1 && v < full - 0.1), JSON.stringify(pads));
  t.check("  its tab on its block all the while (no gliding from the other: each block's own)",
    seen.every((s) => s[1] + s[4] / 2 > s[2] && s[1] + s[4] / 2 < s[3]), JSON.stringify(seen.map((s) => s.slice(1, 4).map(Math.round))));
  t.check("  and ends on its block (its middle within the box)", last && last[1] + last[4] / 2 > last[2] && last[1] + last[4] / 2 < last[3], JSON.stringify(last));
};

scenarios.openline = async (t) => {   // the line from a quote to its ↗: from the colour of the quote's border to the ↗'s
  const line = `(() => { const o = [...document.querySelectorAll(".fw-open")].find(e => getComputedStyle(e, "::before").content !== "none");
    return o ? getComputedStyle(o, "::before").backgroundImage : "none"; })()`;
  await t.open(`#/p/${A}`); await t.select("beta's", { collapse: true }); await t.settle();
  t.check("writing in a quote's one block: faded to faded (in, not selected)", await t.until(`${line} === "linear-gradient(to right, rgba(216, 111, 111, 0.55), rgba(216, 111, 111, 0.55))"`, 1000), await t.js(line));
  await t.open(`#/p/${N}`); await t.select("first words", { collapse: true }); await t.settle();
  t.check("  in one of a quote's blocks: dim (its border's) to faded", await t.until(`${line} === "linear-gradient(to right, rgba(154, 106, 106, 0.38), rgba(216, 111, 111, 0.55))"`, 1000), await t.js(line));
};

scenarios.boxes = async (t) => {   // every block in a thin box; text lines up at every depth; a block selected whole: no blue selection
  const textX = (text) => `(() => { const w = document.createTreeWalker(document.querySelector(".fw-doc"), NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) if (n.data.includes(${JSON.stringify("@")})) { const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 1); return Math.round(r.getBoundingClientRect().left); }
    return null; })()`.replace(JSON.stringify("@"), JSON.stringify(text));
  await t.open(`#/p/${A}`);
  const top = await t.js(textX("first words")), inQuote = await t.js(textX("beta's words"));
  await t.open(`#/p/${S0}`);
  const nested = await t.js(textX("the only block inside"));
  t.check("text starts at one column: a top-level block's, a quote's, two boxes deep", top && top === inQuote && top === nested, JSON.stringify([top, inQuote, nested]));
  t.check("  each in a thin box, a box inside a box a step out", await t.js(`(() => { const a = document.querySelector(".fw-doc .fw-container"), b = a.querySelector(".fw-text");
    return getComputedStyle(b).borderTopWidth === "1px" && b.getBoundingClientRect().left > a.getBoundingClientRect().left; })()`));
  const active = (text) => `(() => { const here = [...document.querySelectorAll(".fw-here")].find(e => e.innerText.includes(${JSON.stringify(text)}));
    if (!here) return "none"; const c = getComputedStyle(here); return c.borderTopColor !== "rgba(0, 0, 0, 0)" && parseFloat(c.paddingTop) > 4
      && c.color === "rgb(221, 218, 211)"; })()`;   // (its box, more room, its text full: --fg)
  await t.select("the only block", { collapse: true });
  t.check("  in a block two boxes deep: drawn as a top-level one (its box, more room)", await t.until(active("the only block"), 1000), await t.js(active("the only block")));
  await t.open(`#/p/${R}`);
  await t.select("jumps over the dog", { collapse: true });
  t.check("  the block you're in: the same weight as the rest (its lines never re-break)", await t.js(`(() => {
    const here = document.querySelector(".fw-here"), rest = [...document.querySelectorAll(".fw-doc .fw-text")].find(e => !e.matches(".fw-here"));
    return getComputedStyle(here).fontWeight === getComputedStyle(rest).fontWeight; })()`));
  t.check("  in a block of a quote showing several: the same", await t.until(active("jumps over the dog"), 1000), await t.js(active("jumps over the dog")));
  t.check("    the quote around it: faint (the path), not the focus's bright red", await t.until(`(() => { const c = getComputedStyle([...document.querySelectorAll(".fw-quote")].find(q => q.innerText.includes("jumps over"))).outlineColor;   // (the path: a hairline outline)
    return c !== "rgb(215, 111, 111)" && c !== "rgba(0, 0, 0, 0)"; })()`, 1000));
  await t.open(`#/p/${A}`);
  await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null; v.state.doc.descendants((n, p) => { if (at === null && n.type.name === "quote") at = p; });
    v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
  t.check("  a quote selected whole: drawn so", await t.until(`!!document.querySelector(".fw-quote.fw-chosen")`, 1000));
  await t.select("beta's words", { collapse: true });
  t.check("  then in it: only where you are is drawn (the page's selection of the quote, left behind, isn't)",
    await t.until(`!document.querySelector(".fw-chosen") && !!document.querySelector(".fw-quote:has(.fw-current) .fw-here")`, 1000));
  t.check("  a quote showing one block: its box is the block's (no second box inside)", await t.until(`(() => {
    const here = document.querySelector(".fw-quote .fw-here"), q = here.closest(".fw-quote");
    return getComputedStyle(here).borderTopColor === "rgba(0, 0, 0, 0)" && getComputedStyle(here).color === "rgb(221, 218, 211)"
      && getComputedStyle(q).borderTopColor === "rgba(216, 111, 111, 0.55)"; })()`, 1000));   // (in it: faded and drawn)
  await t.open(`#/p/${S0}`);
  await t.select("the only block", { collapse: true });
  await t.key("Escape");
  t.check("  selected whole (Esc): drawn so, without the browser's blue selection", await t.until(`!!document.querySelector(".fw-picked, .ProseMirror-selectednode")`, 1000)
    && await t.js(`getComputedStyle(document.querySelector(".fw-picked, .ProseMirror-selectednode").querySelector("*") || document.querySelector(".fw-picked, .ProseMirror-selectednode"), "::selection").backgroundColor === "rgba(0, 0, 0, 0)"`));
};

scenarios.popopen = async (t) => {   // (motion on: ?motion) Turn into a quote and open it: the pop out (the cursor kept, through the quote), then a step into it
  await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}@${A1}` });
  await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
  await t.settle();
  await t.select("first wo", { collapse: true });
  await t.key("e", 12);   // ⌘⇧E
  await t.until(`window.fw?.editor() && window.fw.editor().id !== "${A}" && window.fw.settled()`, 5000);
  t.check("⌘⇧E: popped out and opened, by a step into the quote", (await t.js(`window.fw.lastMove()`))?.dir === "in" && (await t.kids(A))[0].t === "quote",
    JSON.stringify(await t.js(`window.fw.lastMove()`)));
  t.check("  the cursor where it was, in the pericope opened", await t.js(`(() => { const s = window.fw.editor().view.state.selection;
    return s.empty && s.$from.parent.textContent === "first words" && s.$from.parentOffset === 8; })()`),
    await t.js(`(() => { const s = window.fw.editor().view.state.selection; return s.$from.parent.textContent + "|" + s.$from.parentOffset; })()`));
};

scenarios.motion = async (t) => {   // (motion on: ?motion) ⌘O steps into the quote, the page becoming it; ⌘[ steps back out into it
  await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
  await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
  await t.settle();
  await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null;
    v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
    v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
  const clean = `!document.querySelector(".fw-ghost, .fw-veil, .fw-target") && !document.documentElement.matches(".fw-stepping, .fw-swapping")
    && !document.querySelector(".fw-header").style.transform && document.querySelector(".fw-doc > .ProseMirror").style.opacity === ""`;
  await t.key("o", 4);
  await t.until(`window.fw?.editor()?.id === "${B}"`, 5000);
  await t.settle();
  t.check("⌘O: a step in, and nothing of it left on the page", (await t.js(`window.fw.lastMove()`))?.dir === "in" && await t.js(clean),
    JSON.stringify(await t.js(`window.fw.lastMove()`)));
  t.check("  from a quote selected whole: nothing active, no caret, until a key", await t.js(`!document.querySelector(".fw-doc .fw-here") && document.querySelector(".fw-doc > .ProseMirror").classList.contains("fw-selecting")`));
  await t.key("[", 4);
  await t.until(`window.fw?.editor()?.id === "${A}"`, 5000);
  await t.settle();
  t.check("  ⌘[: a step out, nothing of it left", (await t.js(`window.fw.lastMove()`))?.dir === "out" && await t.js(clean));
  t.check("  back from a page opened expanded and untouched (nothing active): the quote selected whole",
    await t.js(`(() => { const c = [...document.querySelectorAll(".fw-doc .fw-chosen")]; return c.length === 1 && c[0].matches('.fw-quote[data-pericope="${B}"]') && !document.querySelector(".fw-doc .fw-here"); })()`),
    await t.js(`[...document.querySelectorAll(".fw-doc .fw-chosen, .fw-doc .fw-here")].map((e) => e.className).join(" | ")`));
  await t.key("]", 4);
  await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
  await t.js(`history.back(); 1`);   // (the browser's own back: a swipe, its button)
  await t.until(`window.fw?.editor()?.id === "${A}" && window.fw.settled()`, 5000);
  t.check("  the browser's own back: a step out too", (await t.js(`window.fw.lastMove()`))?.dir === "out" && await t.js(clean));
  await t.select("beta's", { collapse: true }); await t.settle();
  await t.key("o", 4);
  await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
  t.check("⌘O from the cursor in a quote: the cursor where it was, in the block opened", await t.js(`(() => { const s = window.fw.editor().view.state.selection;
    return s.empty && s.$from.parent.textContent === "beta's words" && s.$from.parentOffset === 6; })()`));
  // (⌘[ and ⌘] land exactly where you were on the page you come back to: the caret, text selected, a block selected
  // whole, the quote selected)
  const inQuote = `(() => { const s = window.getSelection(), q = s.focusNode?.parentElement?.closest(".fw-quote");
    return q && q.dataset.pericope === "${B}" ? [s.anchorNode.textContent, s.anchorOffset, s.focusOffset].join("|") : null; })()`;
  const onB = `(() => { const s = window.getSelection(); return document.querySelector(".fw-doc .fw-chosen")?.textContent.trim()
    || (s.anchorNode && !s.anchorNode.parentElement.closest(".fw-quote") ? [s.anchorNode.textContent, s.anchorOffset, s.focusOffset].join("|") : null); })()`;
  const to = async (key, id) => { await t.key(key, 4); await t.until(`window.fw?.editor()?.id === "${id}" && window.fw.settled()`, 5000); };
  await to("[", A);
  t.check("  ⌘[ from the caret it opened at: the caret in the quote, as it was", await t.js(inQuote) === "beta's words|6|6"
    && await t.js(`!!document.querySelector('.fw-doc .fw-quote[data-pericope="${B}"] .fw-here')`), await t.js(inQuote));
  await to("]", B);
  await t.select("words"); await t.settle();
  await to("[", A);
  t.check("  moved on B (text selected), ⌘[: A as it was left, the caret in the quote", await t.js(inQuote) === "beta's words|6|6", await t.js(inQuote));
  await to("]", B);
  t.check("  ⌘]: B as it was left, the text selected", await t.js(onB) === "beta's words|7|12", await t.js(onB));
  await t.key("Escape"); await t.settle();
  await to("[", A);
  await to("]", B);
  t.check("  a block selected whole on B, ⌘[ then ⌘]: that block selected whole", await t.js(onB) === "beta's words", await t.js(onB));
};

scenarios.motionRepeat = async (t) => {   // (motion on) stepping in and out again and again lands the same each time (the
  // browser's own scroll restoration, and the quote selected only after the step, moved it up the screen each time)
  await t.cdp("Page.navigate", { url: `http://127.0.0.1:${t.port}/?test&motion#/p/${A}` });
  await t.until(`window.fw?.editor()?.id === "${A}"`, 6000);
  await t.settle();
  await t.js(`(() => { const v = window.fw.editor().view; v.focus(); let at = null;
    v.state.doc.descendants((n, pos) => { if (at === null && n.type.name === "quote") at = pos; });
    v.dispatch(v.state.tr.setSelection(window.fw.nodeSel(v.state.doc, at))); return true; })()`);
  const where = `(() => { const q = document.querySelector('.fw-doc .fw-quote[data-pericope="${B}"]'); return q && [Math.round(q.getBoundingClientRect().top), Math.round(scrollY)].join(","); })()`;
  const seen = [], dirs = [];
  for (let k = 0; k < 4; k++) {
    await t.key("o", 4);
    await t.until(`window.fw?.editor()?.id === "${B}" && window.fw.settled()`, 5000);
    dirs.push((await t.js(`window.fw.lastMove()`))?.dir);
    await t.key("[", 4);
    await t.until(`window.fw?.editor()?.id === "${A}" && window.fw.settled()`, 5000);
    dirs.push((await t.js(`window.fw.lastMove()`))?.dir);
    seen.push(await t.js(where));
  }
  t.check("⌘O then ⌘[, four times: each a step, the quote back at the same place on screen, the page scrolled the same (within a pixel: no creeping)",
    dirs.join() === "in,out,in,out,in,out,in,out" && seen[0] && seen.every((s) => s && s.split(",").every((v, k) => Math.abs(v - seen[0].split(",")[k]) <= 1)), `${dirs.join()} · ${seen.join(" | ")}`);
};

scenarios.blockNav = async (t) => {   // a block selected deliberately: ↑/↓ block to block at its level, flowing out past a container's or
  // quote's end; → (or Enter) in a level, onto text to writing; ← out a level, at the top to writing; a quote only
  // arrowed onto still lets the arrow in
  const at = `(() => { const c = [...document.querySelectorAll(".fw-doc .fw-chosen")].filter((e) => !e.parentElement.closest(".fw-chosen"));
    const short = (x) => (x || "").replace(/\\s+/g, " ").trim();
    if (c.length) return c.map((e) => e.matches(".fw-quote") ? "quote:" + e.dataset.pericope.slice(-4) : "block:" + short(e.querySelector(".fw-text, .fw-qtext")?.textContent || e.textContent)).join("+");
    const s = window.getSelection(); return "caret:" + short(s.focusNode?.textContent) + "@" + s.focusOffset; })()`;
  const walk = async (keys) => { const out = []; for (const [k, m = 0] of keys) { await t.key(k, m); await t.settle(); out.push(await t.js(at)); } return out; };
  const same = (got, want) => JSON.stringify(got) === JSON.stringify(want);
  await t.open(`#/p/${R}`);
  await t.select("r words", { collapse: true });
  let got = await walk([["Escape"], ["ArrowDown"], ["ArrowDown"], ["ArrowUp"], ["ArrowUp"]]);
  t.check("Esc, then ↓↓↑↑: block to block (quotes whole, not into them)",
    same(got, ["block:r words", "quote:b000", "quote:c000", "quote:b000", "block:r words"]), JSON.stringify(got));
  await walk([["ArrowDown"], ["ArrowDown"], ["ArrowDown"]]);
  t.check("  ↓ past the page's last block: its foot's search (as from text)", await t.until(`!!document.activeElement?.closest(".fw-on-pericope .fw-suggested")`, 1000));
  await t.select("r words", { collapse: true }); await t.key("Escape"); await t.settle();
  got = await walk([["ArrowDown", 8]]);
  t.check("  Shift+↓ still grows the selection", same(got, ["block:r words+quote:b000"]), JSON.stringify(got));
  await t.key("Escape"); await t.select("r words", { collapse: true }); await t.key("Escape"); await t.settle();
  got = await walk([["Enter"]]);
  t.check("  Enter on a block of text: the caret at its end", same(got, ["caret:r words@7"]), JSON.stringify(got));
  got = await walk([["ArrowDown"], ["ArrowDown"]]);
  t.check("  arrowing from text: a quote reached is gone into, not selected whole, and on into the next",
    same(got, ["caret:beta's words@0", "caret:the quick brown fox@0"]), JSON.stringify(got));
  await t.open(`#/p/${N}`);
  await t.select("after the quotes", { collapse: true });
  got = await walk([["Escape"], ["ArrowUp"], ["Enter"], ["ArrowDown"], ["ArrowDown"], ["ArrowUp"]]);
  t.check("a quote holding blocks: Enter selects its first block; ↓ along them; past its last, out to the block after it; ↑ the quote whole",
    same(got, ["block:after the quotes", "quote:a000", "block:first words", "quote:b000", "block:after the quotes", "quote:a000"]), JSON.stringify(got));
  got = await walk([["ArrowRight"], ["ArrowLeft"], ["ArrowRight"], ["ArrowRight"]]);
  t.check("  → in a level (its first block), ← out (the quote), → in, → onto text: writing at its start",
    same(got, ["block:first words", "quote:a000", "block:first words", "caret:first words@0"]), JSON.stringify(got));
  got = await walk([["Escape"], ["ArrowLeft"], ["ArrowLeft"]]);
  t.check("  ← out of a block in a quote: the quote; ← at the top level: writing, at the start of its text",
    same(got, ["block:first words", "quote:a000", "caret:first words@0"]), JSON.stringify(got));
  await t.open(`#/p/${S0}`);
  await t.select("the only block", { collapse: true });
  got = await walk([["Escape"], ["Escape"], ["Enter"], ["Enter"]]);
  t.check("a container: Esc out a level, Enter back in (its first block), Enter the caret at its end",
    same(got, ["block:the only block inside", "block:the only block inside", "block:the only block inside", "caret:the only block inside@21"]), JSON.stringify(got));
  const chosen = `[...document.querySelectorAll(".fw-doc .fw-chosen")].map((e) => e.matches(".fw-container") ? "container" : "text").join()`;
  const kinds = [];
  for (const k of ["Escape", "ArrowLeft", "ArrowRight", "ArrowRight"]) { await t.key(k); await t.settle(); kinds.push(await t.js(chosen) || await t.js(at)); }
  t.check("  ← out to the container, → back in (its block), → writing at its start",
    same(kinds, ["text", "container", "text", "caret:the only block inside@0"]), JSON.stringify(kinds));
};

scenarios.scrolling = async (t) => {   // the cursor stays on screen: a block taller than the screen is never scrolled to as a whole
  await t.open(`#/p/${T}`);
  await t.select("the quick brown fox", { collapse: true });
  for (let k = 0; k < 45; k++) { await t.key("Enter", 8); await t.type(`line ${k}`); }   // (⇧↵: one block, 46 lines)
  await t.settle();
  const onScreen = `(() => { const v = window.fw.editor().view, c = v.coordsAtPos(v.state.selection.head); return c.top >= 0 && c.bottom <= innerHeight; })()`;
  await t.open(`#/p/${T}@${T1}`);
  t.check("opened at a block taller than the screen: the cursor on screen (at its start)", await t.js(onScreen),
    await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head).top, innerHeight, scrollY])`));
  await t.select("line 44", { collapse: true });
  await t.key("ArrowDown");
  await t.settle();
  // (until: between text blocks the browser moves the caret itself, and ProseMirror reads it on a later selectionchange)
  t.check("  ↓ out of its last line into the next block: the cursor still on screen", await t.until(`${onScreen} && window.fw.editor().context().block?.id === "${T2}"`, 2000), await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head), innerHeight, scrollY, document.documentElement.scrollHeight, window.fw.editor().context().block?.id])`));
  await t.key("ArrowUp");
  await t.settle();
  t.check("  ↑ back into it, at its last line: on screen", await t.until(`${onScreen} && window.fw.editor().context().block?.id === "${T1}"`, 2000), await t.js(`JSON.stringify([window.fw.editor().view.coordsAtPos(window.fw.editor().view.state.selection.head), innerHeight, scrollY, document.documentElement.scrollHeight, window.fw.editor().context().block?.id])`));
};

scenarios.tabs = async (t) => {   // the focus's tab: outlined; selected whole, filled; a quote's ↗ the same
  const tab = `document.querySelector(".fw-tabs .fw-tab-focus")`;
  await t.open(`#/p/${A}`);
  await t.select("first words", { collapse: true });
  t.check("in a block: its number a tab, bright (outlined), a line to its border", await t.until(`!!${tab} && ${tab}.textContent === "1" && !${tab}.matches(".fw-tab-filled") && !!document.querySelector(".fw-tabs .fw-tab-line")`, 1000),
    await t.js(`[...document.querySelectorAll(".fw-tabs > *")].map(e => e.className + ":" + e.textContent).join(" | ")`));
  await t.key("Escape");
  t.check("  selected whole: the tab filled", await t.until(`!!${tab} && ${tab}.matches(".fw-tab-filled")`, 1000));
  t.check("  selected whole: no caret (one focus)", await t.until(`!!document.querySelector(".fw-selecting") && getComputedStyle(document.querySelector(".fw-selecting")).caretColor === "rgba(0, 0, 0, 0)"`, 1000));
  await t.select("beta's words", { collapse: true });
  t.check("in a quote: its ↗ a tab (outlined, a line to its border)", await t.until(`(() => { const o = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open");
    return getComputedStyle(o).outlineStyle === "solid" && getComputedStyle(o, "::before").borderTopStyle === "solid"; })()`, 1000));
  await t.key("Escape");
  t.check("  only the ↗ where ⌘O goes is a tab", await t.js(`[...document.querySelectorAll(".fw-doc .fw-open")].filter(o => getComputedStyle(o).outlineStyle === "solid").length === 1`));
  t.check("  the quote selected whole: its ↗ filled, its arrow the page's colour", await t.until(`(() => { const o = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open");
    return getComputedStyle(o).backgroundColor === "rgb(215, 111, 111)" && getComputedStyle(o).color === "rgb(17, 17, 17)"; })()`, 1000));
  await t.shot("tab-arrow.png", await t.js(`(() => { const r = document.querySelector(".fw-doc .fw-quote > .fw-top > .fw-open").getBoundingClientRect();
    return { x: r.x - 30, y: r.y - 8, width: r.width + 38, height: r.height + 16, scale: 8 }; })()`));
};

scenarios.letterTabs = async (t) => {   // every block on your path a tab in the gutter: numbered, lettered, ...; the focus's bright
  // (nested: a quote of alpha [first words, a quote of beta [beta's words]], then "after the quotes")
  const tabs = `[...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.textContent + (e.matches(".fw-tab-focus") ? "*" : "")).join(" ")`;
  await t.open(`#/p/${N}`);
  await t.select("after the quotes", { collapse: true });
  t.check("in a top-level block: its number, a tab", await t.until(`${tabs} === "2*"`, 1000), await t.js(tabs));
  await t.select("first words", { collapse: true });
  t.check("in a block inside a quote (not itself a quote): the quote's number, then its letter, the focus's bright",
    await t.until(`${tabs} === "1 a*"`, 1000), await t.js(tabs));
  t.check("  the quote starting on its first block's line: its tab above the block's, as they nest, each line on its own box, padded from its ends",
    await t.js(`(() => { const ts = [...document.querySelectorAll(".fw-tabs .fw-tab")], ls = [...document.querySelectorAll(".fw-tabs .fw-tab-line")];
      const [q, b] = ts.map((x) => x.getBoundingClientRect()), mid = (l) => l.getBoundingClientRect().top;
      const qb = document.querySelector(".fw-doc .fw-quote").getBoundingClientRect(), bb = document.querySelector(".fw-current .fw-here").getBoundingClientRect();
      const pad = 0.3 * q.height;   // (each line padded inside its box at both ends, things pushed down to make it)
      return q.bottom <= b.top && mid(ls[0]) >= qb.top + pad && mid(ls[0]) <= qb.bottom - pad && mid(ls[1]) >= bb.top + pad && mid(ls[1]) <= bb.bottom - pad; })()`),
    await t.js(`[...document.querySelectorAll(".fw-tabs > *")].map((x) => x.className + "@" + Math.round(x.getBoundingClientRect().top)).join(" ")`));
  const qTop = `[...document.querySelectorAll(".fw-tabs .fw-tab")].find(e => e.textContent === "1")?.getBoundingClientRect().top`;
  const was = await t.js(qTop);
  await t.key("Escape"); await t.key("Escape");   // (the block whole, then the quote around it)
  // (placed by the page, not by which tabs show; moved only a little, by its first block's room going)
  t.check("  stepping out to the quote: its tab stays where it was (bar the block's room going)",
    await t.until(`!!document.querySelector(".fw-tab-filled") && document.querySelector(".fw-tab-filled").textContent === "1"`, 1000)
    && Math.abs((await t.js(qTop)) - was) < 4, `${was} → ${await t.js(qTop)}`);
  await t.select("beta's words", { collapse: true });
  t.check("in a quote showing one block: the quote's tab is the focus (its block has none of its own)", await t.until(`${tabs} === "1 b*"`, 1000), await t.js(tabs));
  const centred = `(() => { const tab = document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect();
    const n = [...document.querySelectorAll(".fw-doc .fw-quote .fw-quote .fw-text")].find(e => e.textContent.includes("beta's")).firstChild.firstChild || [...document.querySelectorAll(".fw-doc .fw-quote .fw-quote .fw-text")].find(e => e.textContent.includes("beta's")).firstChild;
    const r = document.createRange(); r.setStart(n, 0); r.setEnd(n, 1); const l = r.getBoundingClientRect();
    return Math.abs((tab.top + tab.height / 2) - (l.top + l.height / 2)) <= 1; })()`;
  t.check("  the focus's tab centred on its block's first line", await t.js(centred));
  t.check("  every tab's line meets its own box (its middle within the box's top and bottom)", await t.js(`(() => {
    const lines = [...document.querySelectorAll(".fw-tabs .fw-tab-line")];
    return lines.every((l) => { const y = l.getBoundingClientRect().top, x = l.getBoundingClientRect().right;
      const box = [...document.querySelectorAll(".fw-doc .fw-text, .fw-doc .fw-quote, .fw-doc .fw-container")].find((b) => Math.abs(b.getBoundingClientRect().left - x) < 2 && y >= b.getBoundingClientRect().top && y <= b.getBoundingClientRect().bottom);
      return !!box; }); })()`));
  t.check("  tabs never overlap (one on another's line moves above or below it, clear)", await t.js(`(() => { const r = [...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.getBoundingClientRect());
    return r.every((x, i) => i === 0 || x.top >= r[i - 1].bottom); })()`));
  t.check("  the quote around it (the path): faint, not the focus's bright red", await t.until(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).outlineColor === "rgba(154, 106, 106, 0.38)"`, 1000),
    await t.js(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote")).outlineColor`));
  await t.select("first words", { collapse: true, start: true });
  await t.settle();
  const at = await t.js(`document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect().top`);
  await t.key("ArrowRight"); await t.key("ArrowRight");
  await t.settle();
  const tabsAt = `[...document.querySelectorAll(".fw-tabs .fw-tab")].map(e => e.textContent + "@" + Math.round(e.getBoundingClientRect().top)).join(" ")`;
  t.check("  moving within the block: its tab stays put", Math.abs((await t.js(`document.querySelector(".fw-tabs .fw-tab-focus").getBoundingClientRect().top`)) - at) < 1,
    `before ${at} after ${await t.js(tabsAt)}`);
  await t.select("beta's words", { collapse: true });
  await t.key("Escape");   // (beta's quote selected whole, in alpha's quote's editor)
  t.check("  a quote selected inside another: only its ↗ is a tab (⌘O opens it), not the one around it", await t.until(`(() => {
    const on = [...document.querySelectorAll(".fw-doc .fw-open")].filter(o => getComputedStyle(o).outlineStyle === "solid");
    return on.length === 1 && on[0].closest(".fw-quote").matches(".fw-chosen"); })()`, 1000));
  await t.select("first words", { collapse: true, start: true });
  const one = await t.js(`(() => { const r = [...document.querySelectorAll(".fw-tabs .fw-tab")].find(e => e.textContent === "1").getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`);
  await t.click(one[0], one[1]);
  t.check("  a click on a path tab (the quote around you): that quote selected whole, its tab now the focus, filled",
    await t.until(`!!document.querySelector(".fw-doc > .ProseMirror > .fw-quote.fw-chosen") && document.querySelector(".fw-tabs .fw-tab-focus")?.matches(".fw-tab-filled")`, 1000));
  t.check("  a top-level block with a tab: its plain number hidden under it", await t.js(`getComputedStyle(document.querySelector(".fw-doc > .ProseMirror > .fw-quote"), "::before").visibility === "hidden"`));
};
